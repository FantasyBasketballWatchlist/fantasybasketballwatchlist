"""Can we predict who will miss more games next season, beyond BPV's current availability estimate?

Run:  python -m analysis.test_availability        (writes analysis/test_availability.json)

Pool: players with 20+ games and 20+ minutes per game the season before (a season missed entirely
counts as 0%). Each candidate is a correction to the current estimate, fitted on the other seasons
(leave-one-season-out) and scored by mean absolute error on availability.
Two baselines, because the app uses both:
  history: the current estimate (recent seasons, decay 0.5, 123 games of league average)
  ESPN:    what the app uses before the season when ESPN matches: min(1, 0.86 x ESPN games / 82)
Adoption rule (set before testing): 95% interval (resampling player-seasons) excludes 0 in favor
AND better in the majority of held-out seasons.

Candidates
  A1 age (straight line, and 32+ only)          A2 minutes load last season (mpg, total minutes)
  A3 serious/recurring injury types on past reports (any serious, knee, back, foot/ankle/Achilles,
     hamstring/calf soft tissue)
  A4 how he finished last season: team games missed after his last appearance
  A5 how absences were spread: number of separate absences, share in long stretches
  A6 trend: last season's availability minus the season before
  A7 body size: weight, height, weight per inch
  A8 usage rate
  A9 injury absences vs rest absences last season (from reports) -- tested before as a pair (tie);
     here each alone
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import robustness as rb
from analysis import test_espn_projections as tep
from analysis import test_injury_reports as tir
from analysis import test_misc as tm
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_availability.json")
TARGETS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
PART_PATTERNS = {"knee": r"knee|acl|mcl|meniscus|patell", "back": r"back|spine|lumbar|disc",
                 "foot_ankle": r"foot|ankle|achilles|toe|heel|plantar", "soft_tissue": r"hamstring|calf|groin|adductor"}


def trailing_gap(pg, tg, season):
    """Share of his team's games played after his last appearance of the season."""
    g = pg[season].sort_values("GAME_DATE").groupby("PLAYER_ID").last()
    ends = tg[season].groupby("TEAM_ID").GAME_DATE.apply(sorted)
    out = {}
    for pid, r in g.iterrows():
        dates = ends.get(r.TEAM_ID)
        if dates is not None:
            out[pid] = sum(d > r.GAME_DATE for d in dates) / len(dates)
    return out


def frame(pg, tg):
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    rep, _ = tir.load_reports(pg)
    inj = rep[(rep["Current Status"] == "Out") & (rep.category == "injury")]
    ab = tir.season_absences(pg, tg, rep)
    names = tep.name_map(pg)
    espn = {}
    for t, year in tep.ESPN_SEASONS.items():
        e = tep.projections(year)
        e["PLAYER_ID"] = e.name.map(tep.key).map(names)
        espn[t] = e.dropna(subset=["PLAYER_ID"]).drop_duplicates("PLAYER_ID").set_index("PLAYER_ID").espn_gp
    rows = []
    for t in TARGETS:
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        prev2 = bt.SEASONS[bt.SEASONS.index(t) - 2]
        p_league, _ = rb.league_before(hist, t)
        p_hat = bpv.predict_availability(hist, bt.SEASONS, prev, 0.5, 123, p_league)
        hp = hist[(hist.season == prev) & (hist.mpg >= 20) & (hist.played >= 20)].set_index("PLAYER_ID")
        h2 = hist[hist.season == prev2].set_index("PLAYER_ID")
        ht = hist[hist.season == t].set_index("PLAYER_ID")
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID").AGE
        bio = nba_data.player_bio(prev).set_index("PLAYER_ID")
        trail = trailing_gap(pg, tg, prev)
        past = inj[inj.season.map(bt.SEASONS.index) < bt.SEASONS.index(t)]
        for pid in hp.index.intersection(ht.index):
            h = hp.loc[pid]
            reasons = " ".join(past[past.PLAYER_ID == pid].Reason.fillna("").str.lower())
            a = ab.loc[(prev, pid)] if (prev, pid) in ab.index else pd.Series(dtype=float)
            row = {"target": t, "PLAYER_ID": pid, "availability": float(ht.loc[pid].availability),
                   "p_hat": float(p_hat.get(pid, p_league)),
                   "espn": min(1.0, 0.86 * espn[t][pid] / 82) if t in espn and pid in espn[t].index else np.nan,
                   "age": ages.get(pid, np.nan), "mpg": h.mpg, "total_min": h.mpg * h.played / 1000,
                   "trail": trail.get(pid, 0.0), "spells": h.spells / max(h.possible, 1) * 82,
                   "long_share": h.missed_long / h.missed if h.missed > 0 else np.nan,
                   "trend": h.availability - h2.availability.get(pid, np.nan) if pid in h2.index else np.nan,
                   "weight": bio.PLAYER_WEIGHT.get(pid, np.nan), "height": bio.PLAYER_HEIGHT_INCHES.get(pid, np.nan),
                   "usage": bio.USG_PCT.get(pid, np.nan),
                   "reports": prev >= "2021-22"}
            row["weight_per_inch"] = row["weight"] / row["height"] if row["height"] else np.nan
            row["age32"] = max(0.0, row["age"] - 31) if pd.notna(row["age"]) else np.nan
            row["serious"] = float(bool(pd.Series([reasons]).str.contains(bpv.SERIOUS_INJURY).iloc[0])) if row["reports"] else np.nan
            for part, pat in PART_PATTERNS.items():
                row[part] = float(bool(pd.Series([reasons]).str.contains(pat).iloc[0])) if row["reports"] else np.nan
            row["inj_absent"] = float(a.get("injury", 0)) / h.possible if row["reports"] else np.nan
            row["rest_absent"] = float(a.get("rest", 0)) / h.possible if row["reports"] else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def judge(d, new, old, target="availability"):
    d = d.reset_index(drop=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    b = tm.boot(d, np.abs(d[new] - d[target]), np.abs(d[old] - d[target]), key="key")
    per = {s: float((np.abs(g[new] - g[target]) - np.abs(g[old] - g[target])).mean()) for s, g in d.groupby("target")}
    wins = sum(v < 0 for v in per.values())
    v = tm.verdict(b)
    return {"n": len(d), "mae_base": float(np.abs(d[old] - d[target]).mean()), "minus_base": b, "per_season": per,
            "seasons_better": wins, "verdict": "better" if v == "better" and wins > len(per) / 2 else ("tie" if v == "better" else v)}


def correct(d, base, features):
    """Leave-one-season-out least-squares correction of the base on the features (centered on training)."""
    d = d.dropna(subset=[base] + features).copy()
    d["new"] = np.nan
    coefs = {}
    for t in d.target.unique():
        tr, m = d[d.target != t], d.target == t
        if len(tr) < 50 or tr.target.nunique() < 2:
            continue
        mu = tr[features].mean()
        X = (tr[features] - mu).to_numpy()
        y = (tr.availability - tr[base]).to_numpy()
        X1 = np.column_stack([np.ones(len(X)), X])
        b, *_ = np.linalg.lstsq(X1, y, rcond=None)
        d.loc[m, "new"] = np.clip(d.loc[m, base] + b[0] + (d.loc[m, features] - mu).to_numpy() @ b[1:], 0, 1)
        coefs[t] = [round(float(x), 4) for x in b[1:]]
    d = d.dropna(subset=["new"])
    # Intercept-only correction, so a feature has to beat a plain recentering of the base.
    return d, coefs


def evaluate(d, base, features):
    scored, coefs = correct(d, base, features)
    # Compare with the base recentered (intercept only) on the same rows, to isolate the feature.
    rec = recenter(scored, base)
    return {"features": features, "coefs_by_fold": coefs, **judge(rec, "new", "recentered")}


def recenter(d, base):
    d = d.copy()
    d["recentered"] = np.nan
    for t in d.target.unique():
        tr = d[d.target != t]
        d.loc[d.target == t, "recentered"] = np.clip(d.loc[d.target == t, base] + (tr.availability - tr[base]).mean(), 0, 1)
    return d


CANDIDATES = {
    "A1_age": ["age"], "A1_age_32plus": ["age32"],
    "A2_mpg": ["mpg"], "A2_total_minutes": ["total_min"],
    "A3_serious_before": ["serious"], "A3_knee": ["knee"], "A3_back": ["back"],
    "A3_foot_ankle_achilles": ["foot_ankle"], "A3_soft_tissue": ["soft_tissue"],
    "A4_missed_end_of_season": ["trail"],
    "A5_number_of_absences": ["spells"], "A5_long_share": ["long_share"],
    "A6_trend": ["trend"],
    "A7_weight": ["weight"], "A7_height": ["height"], "A7_weight_per_inch": ["weight_per_inch"],
    "A8_usage": ["usage"],
    "A9_injury_absences": ["inj_absent"], "A9_rest_absences": ["rest_absent"],
}


def main():
    pg, tg = bt.load()
    d = frame(pg, tg)
    res = {"n_rows": len(d), "n_with_espn": int(d.espn.notna().sum()),
           "mae_history": float(np.abs(d.p_hat - d.availability).mean()),
           "mae_espn_vs_history_same_rows": {
               "espn": float(np.abs(d.espn - d.availability)[d.espn.notna()].mean()),
               "history": float(np.abs(d.p_hat - d.availability)[d.espn.notna()].mean())}}
    for base in ("p_hat", "espn"):
        res[base] = {"recentering_alone": judge(recenter(d.dropna(subset=[base]), base), "recentered", base)}
        print(base, "recentering", res[base]["recentering_alone"]["verdict"], res[base]["recentering_alone"]["minus_base"], flush=True)
        for name, feats in CANDIDATES.items():
            try:
                r = evaluate(d, base, feats)
            except Exception as e:
                r = {"error": str(e)}
            res[base][name] = r
            print(base, name, r.get("verdict"), r.get("minus_base", {}).get("diff"), r.get("minus_base", {}).get("ci95"),
                  r.get("seasons_better"), "/", len(r.get("per_season", {})), flush=True)
    d.to_csv(os.path.join(nba_data.CACHE_DIR, "availability_features.csv"), index=False)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
