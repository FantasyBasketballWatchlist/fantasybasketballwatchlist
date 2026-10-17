"""Can ESPN's own preseason fantasy projections improve or benchmark BPV's preseason production?

Run:  python -m analysis.test_espn_projections      (prints results; writes nothing but the ESPN cache)

Data: ESPN's public, undocumented fantasy API (read-only, no login), one request per season:
  GET https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/segments/0/leaguedefaults/3
      ?view=kona_player_info
  header X-Fantasy-Filter: {"players":{"limit":1000,"sortPercOwned":{"sortPriority":1,"sortAsc":false}}}
Cached as data/cache/espn_kona_{year}.json (per-game logs, statSplitTypeId 5, dropped to save space).
The projection is the stats entry with statSourceId 1, statSplitTypeId 0, seasonId == year
(id "10{year}"). leaguedefaults does not return appliedTotal, so FPTS are recomputed from the raw
projected stat ids with bpv.SCORING (ESPN default points scoring).

Is it preseason? Checked by hand (see PRESEASON_CHECK): for 2022, 2024, 2025, 2026 the projected games
reflect only injuries known before opening night (Kawhi 13 GP in 2021-22, Murray 31, Haliburton 1 in
2025-26, Kyrie 43) and ignore in-season events (Embiid 64 GP in 2023-24, 60 in 2024-25; Wembanyama 70
in 2024-25; Paul George 22.2 ppg projected vs 16.2 actual). For 2023 (2022-23) every projection has
~40 games (median 39): it is a rest-of-season projection frozen mid-season, not a preseason one, so
2022-23 is excluded from the ESPN comparisons.

Tests (target seasons 2021-22, 2023-24, 2024-25, 2025-26)
  1. FPTS/game accuracy: ESPN projected FPTS/game vs BPV preseason production (last season FPTS/g +
     age-bucket adjustment fitted leave-one-season-out, as in analysis.preseason_production) against
     actual FPTS/g. Players with 20+ games in T and T-1, 15+ mpg in T-1, and an ESPN projection.
  2. Blend w*ESPN + (1-w)*BPV, w tuned leave-one-season-out over the four ESPN seasons.
  3. Rank correlation with actual season totals and simulated snake drafts (analysis.backtest).
"""
import json
import math
import os
import re
import sys
import time
import warnings

import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis import backtest as bt  # noqa: E402
from analysis import preseason_production as pp  # noqa: E402
from analysis import test_misc as tm  # noqa: E402
import bpv  # noqa: E402
import nba_data  # noqa: E402
import ratings  # noqa: E402

warnings.filterwarnings("ignore")
URL = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/segments/0/"
       "leaguedefaults/3?view=kona_player_info")
FILTER = {"players": {"limit": 1000, "sortPercOwned": {"sortPriority": 1, "sortAsc": False}}}
# ESPN stat ids -> nba_data columns (verified against actual season totals, e.g. Curry 2022-23).
STAT_IDS = {"PTS": "0", "BLK": "1", "STL": "2", "AST": "3", "REB": "6", "TOV": "11", "FGM": "13",
            "FGA": "14", "FTM": "15", "FTA": "16", "FG3M": "17"}
GP_ID = "42"
ESPN_SEASONS = {"2021-22": 2022, "2023-24": 2024, "2024-25": 2025, "2025-26": 2026}   # 2022-23 excluded
ALL_FRAMES = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
PRESEASON_CHECK = {2022: ["Kawhi Leonard", "Jamal Murray", "Klay Thompson"],
                   2023: ["Stephen Curry", "Paolo Banchero", "LeBron James"],
                   2024: ["Joel Embiid", "Ja Morant"], 2025: ["Victor Wembanyama", "Joel Embiid", "Paul George"],
                   2026: ["Tyrese Haliburton", "Kyrie Irving", "Luka Doncic"]}


def fetch(year):
    path = os.path.join(nba_data.CACHE_DIR, f"espn_kona_{year}.json")
    if not os.path.exists(path):
        r = requests.get(URL.format(year=year), headers={"X-Fantasy-Filter": json.dumps(FILTER)}, timeout=120)
        r.raise_for_status()
        d = r.json()
        for p in d["players"]:
            p["player"]["stats"] = [s for s in p["player"].get("stats", []) if s["statSplitTypeId"] != 5]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(d, f)
        time.sleep(1)
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fpts(stats):
    return sum(w * stats.get(STAT_IDS[k], 0.0) for k, w in bpv.SCORING.items())


def projections(year):
    rows = []
    for p in fetch(year)["players"]:
        pl = p["player"]
        for s in pl.get("stats", []):
            if s["statSourceId"] == 1 and s["statSplitTypeId"] == 0 and s["seasonId"] == year:
                gp = s["stats"].get(GP_ID, 0.0)
                avg = s.get("averageStats") or {}
                fpg = fpts(avg) if avg else (fpts(s["stats"]) / gp if gp else np.nan)
                rows.append({"name": pl["fullName"], "espn_gp": gp, "espn_fpg": fpg, "espn_total": fpts(s["stats"]),
                             "espn_pts": avg.get("0", np.nan)})
    return pd.DataFrame(rows)


def key(name):
    n = ratings.normalize_name(name).replace("-", " ").replace("'", "")
    return re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", n).strip()


def name_map(pg):
    rows = pd.concat([g[["PLAYER_ID", "PLAYER_NAME"]] for g in pg.values()]).drop_duplicates("PLAYER_ID", keep="last")
    return {key(n): pid for pid, n in zip(rows.PLAYER_ID, rows.PLAYER_NAME)}


def attach(df, proj, names):
    proj = proj.copy()
    proj["PLAYER_ID"] = proj.name.map(key).map(names)
    matched = proj.dropna(subset=["PLAYER_ID"]).drop_duplicates("PLAYER_ID")
    return df.merge(matched[["PLAYER_ID", "espn_fpg", "espn_gp", "espn_total"]], on="PLAYER_ID", how="left"), \
        {"espn_players": len(proj), "matched": int(proj.PLAYER_ID.notna().sum()),
         "unmatched_examples": proj[proj.PLAYER_ID.isna()].name.head(8).tolist()}


def preseason_check():
    out = {}
    for year, names in PRESEASON_CHECK.items():
        p = projections(year).set_index("name")
        out[year] = {"median_projected_gp": float(p.espn_gp.median()),
                     "examples": {n: {"gp": float(p.loc[n, "espn_gp"]), "pts": round(float(p.loc[n, "espn_pts"]), 1)}
                                  for n in names if n in p.index}}
    return out


def main():
    pg, tg = bt.load()
    names = name_map(pg)
    res = {"preseason_check": preseason_check(), "matching": {}}

    # ---------------------------------------------------------------- 1-2. FPTS/game accuracy and blend
    tab = pp.season_table(pg)
    frames = {t: pp.frame(tab, t) for t in ALL_FRAMES}
    for t, year in ESPN_SEASONS.items():
        frames[t], res["matching"][t] = attach(frames[t], projections(year), names)
    scored = []
    for t in ESPN_SEASONS:
        tr = pd.concat([frames[x] for x in ALL_FRAMES if x != t], ignore_index=True)
        tr["last"] = tr.fp1
        curve = pp.fit_age_curve(tr, "last")
        te = frames[t].copy()
        te["last"] = te.fp1
        te["bpv"] = pp.with_age(te, "last", curve)
        res["matching"][t]["frame_players"] = len(te)
        res["matching"][t]["frame_with_espn"] = int(te.espn_fpg.notna().sum())
        scored.append(te.dropna(subset=["espn_fpg"]))
    df = pd.concat(scored, ignore_index=True)

    grid = np.round(np.arange(0, 1.001, 0.05), 2)
    df["blend"], df["w"] = np.nan, np.nan
    for t in ESPN_SEASONS:
        tr = df[df.target != t]
        w = min(grid, key=lambda w: bt.mae(w * tr.espn_fpg + (1 - w) * tr.bpv, tr.actual))
        m = df.target == t
        df.loc[m, "blend"] = w * df.loc[m, "espn_fpg"] + (1 - w) * df.loc[m, "bpv"]
        df.loc[m, "w"] = w
    df["blend50"] = 0.5 * df.espn_fpg + 0.5 * df.bpv
    # ESPN minus its average over-projection in the other seasons (a leave-one-season-out bias fix).
    df["espn_debiased"] = np.nan
    for t in ESPN_SEASONS:
        m = df.target == t
        df.loc[m, "espn_debiased"] = df.loc[m, "espn_fpg"] - (df.espn_fpg - df.actual)[~m].mean()
    models = ["last", "bpv", "espn_fpg", "espn_debiased", "blend", "blend50"]
    err = {m: np.abs(df[m] - df.actual) for m in models}
    res["fpg"] = {
        "n": len(df), "n_players": int(df.PLAYER_ID.nunique()),
        "mae": {m: bt.mae(df[m], df.actual) for m in models},
        "mae_by_season": {t: {m: bt.mae(g[m], g.actual) for m in models} | {"n": len(g)} for t, g in df.groupby("target")},
        "spearman_fpg": {m: bt.spearman(df[m], df.actual) for m in models},
        "blend_w_by_heldout_season": df.groupby("target").w.first().to_dict(),
        "blend_w_all_seasons": float(min(grid, key=lambda w: bt.mae(w * df.espn_fpg + (1 - w) * df.bpv, df.actual))),
        "espn_minus_bpv": tm.boot(df, err["espn_fpg"], err["bpv"]),
        "blend_minus_bpv": tm.boot(df, err["blend"], err["bpv"]),
        "blend50_minus_bpv": tm.boot(df, err["blend50"], err["bpv"]),
        "blend_minus_espn": tm.boot(df, err["blend"], err["espn_fpg"]),
        "espn_debiased_minus_bpv": tm.boot(df, err["espn_debiased"], err["bpv"]),
        "bias_mean_pred_minus_actual": {m: float((df[m] - df.actual).mean()) for m in models},
    }
    for b in ("espn_minus_bpv", "blend_minus_bpv", "blend50_minus_bpv", "blend_minus_espn", "espn_debiased_minus_bpv"):
        res["fpg"][b]["verdict"] = tm.verdict(res["fpg"][b])
    print(json.dumps(res["fpg"], indent=1, default=float), flush=True)

    # ---------------------------------------------------------------- 3. season totals: rank correlation and drafts
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    w_all = res["fpg"]["blend_w_by_heldout_season"]
    res["totals"] = {}
    for t, year in ESPN_SEASONS.items():
        pdf, R = bt.preseason_frame(pg, hist, t, ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K,
                                    league_p, league_q, age_curve=bt.age_curve_before(pg, t))
        pdf["PLAYER_ID"] = pdf.index
        pdf = pdf.reset_index(drop=True)
        pdf, _ = attach(pdf, projections(year), names)
        pdf = pdf.set_index("PLAYER_ID", drop=False)
        # bpv_value is linear in production: recover BPV's age-adjusted production, blend it, convert back.
        prod = (pdf["BPV + age"] - (1 - pdf.p_hat) * league_q * R) / pdf.p_hat
        w = w_all[t]
        pdf["BPV blend (ESPN FPG)"] = bpv.bpv_value(prod.where(pdf.espn_fpg.isna(), w * pdf.espn_fpg + (1 - w) * prod),
                                                    pdf.p_hat, league_q, R)
        pdf["ESPN proj total"] = pdf.espn_total
        pool = pdf[(pdf.S >= 15) & pdf.espn_total.notna()]
        cols = ["BPV (replacement-level)", "BPV + age", "BPV blend (ESPN FPG)", "ESPN proj total", "Last season total FPTS"]
        block = {"players": len(pool), "blend_w": w,
                 "spearman_vs_actual_total": {c: bt.spearman(pool[c], pool.actual_total) for c in cols}}
        sim = pdf.copy()
        for c in cols:
            sim[c] = sim[c].fillna(-math.inf)
        block["draft_sim_total"] = {k: v["mean"] for k, v in bt.simulate_drafts(sim, cols, n_sims=1000).items()}
        res["totals"][t] = block
        print(t, json.dumps(block, default=float), flush=True)
    res["totals_mean"] = {
        "spearman": {c: float(np.mean([b["spearman_vs_actual_total"][c] for b in res["totals"].values()])) for c in cols},
        "draft_sim": {c: float(np.mean([b["draft_sim_total"][c] for b in res["totals"].values()])) for c in cols}}
    print(json.dumps({k: res[k] for k in ("preseason_check", "matching", "totals_mean")}, indent=1, default=float))


if __name__ == "__main__":
    main()
