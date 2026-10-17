"""Holdout test: today's frozen BPV formula on 2014-15..2018-19, seasons never used for any decision.

Run:  python -m analysis.holdout        (writes analysis/holdout.json)

The rules and pass criteria were written first, in docs/holdout-preregistration.md (P1-P9).
Nothing here is fitted on the target seasons; league-level values come from seasons before each target.
"""
import json
import os
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import robustness as rb
from analysis import test_availability3 as t3
from analysis import test_minutes_model as tmm
from analysis import test_misc as tm
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdout.json")
bt.SEASONS = [nba_data.season_string(y) for y in range(2009, 2019)]
TARGETS = ["2014-15", "2015-16", "2016-17", "2017-18", "2018-19"]

# Frozen constants (ratings.py, 2026-09-28).
AGE_CURVE = ratings.AGE_CURVE
CROWDING = ratings.CROWDING_COEF
RECAL = ratings.RECALIBRATION
SHOOT = ratings.SHOOTING_REGRESSION
PRIOR_K, ROOKIE_K = ratings.PRIOR_SEASON_K, ratings.ROOKIE_K
MIN_W, EFF_W = 0.3, 0.1
STREAK = (ratings.ABSENCE_STREAK_INTERCEPT, ratings.ABSENCE_STREAK_COEF, ratings.ABSENCE_STREAK_CAP)


def efg(fgm, fg3m, fga):
    return (fgm + 0.5 * fg3m) / np.maximum(fga, 1)


def age_adj(ages, pid):
    a = ages.get(pid)
    return AGE_CURVE[bpv.age_bucket(a)] if a is not None and pd.notna(a) else 0.0


def per_season(d, new, old, target, loss=np.abs, season="season"):
    return {s: float((loss(g[new] - g[target]) - loss(g[old] - g[target])).mean()) for s, g in d.groupby(season)}


def wins(per):
    return sum(v < 0 for v in per.values())


# ------------------------------------------------------------------ preseason (P1-P4)
def preseason(pg, tg, hist):
    out = {"rank_corr": {}, "per_game": [], "drafts": {}}
    for t in TARGETS:
        p_league, q_league = rb.league_before(hist, t)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        df, R = bt.preseason_frame(pg, hist, t, 0.5, 123, p_league, q_league, age_curve=AGE_CURVE)
        h_prev = hist[(hist.season == prev) & (hist.played >= 20)].set_index("PLAYER_ID")
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID")["AGE"]
        ctx = tmm.roster_context(pg, t)
        eligible = h_prev.mpg.reindex(df.index) >= 15
        adj = pd.Series([age_adj(ages, pid) for pid in df.index], index=df.index).where(eligible, 0.0)
        crowd = (CROWDING * ctx.crowding.reindex(df.index).fillna(0)).where(eligible, 0.0)
        df["prod_full"] = df.S + adj + crowd
        df["Full BPV"] = bpv.bpv_value(df.prod_full, df.p_hat, q_league, R)
        cols = {"naive": "Last season total FPTS", "original": "M5 80/20 x career GP%",
                "revised": "BPV (replacement-level)", "full": "Full BPV"}
        out["rank_corr"][t] = {k: bt.spearman(df[c], df.actual_total) for k, c in cols.items()}
        h_t = hist[(hist.season == t) & (hist.played >= 20)].set_index("PLAYER_ID")
        both = df.index.intersection(h_t.index)
        for pid in both:
            out["per_game"].append({"season": t, "key": f"{pid}{t}", "actual": h_t.loc[pid, "fpts_pg"],
                                    "revised": df.loc[pid, "S"], "full": df.loc[pid, "prod_full"]})
        field = [cols["naive"], cols["original"], "M3 x career GP%", cols["revised"], cols["full"]]
        sims = bt.simulate_drafts(df.dropna(subset=field), field)
        out["drafts"][t] = {k: sims[c]["mean"] for k, c in cols.items()}
        print(t, "preseason", {k: round(v, 3) for k, v in out["rank_corr"][t].items()}, flush=True)
    pgd = pd.DataFrame(out["per_game"])
    rc = out["rank_corr"]
    res = {
        "rank_corr": rc, "drafts": out["drafts"],
        "P1_full_vs_naive_rank": {"seasons_better": sum(rc[t]["full"] > rc[t]["naive"] for t in TARGETS)},
        "P2_full_vs_original_rank": {"seasons_better": sum(rc[t]["full"] > rc[t]["original"] for t in TARGETS)},
        "P3_additions": {"rank_seasons_better": sum(rc[t]["full"] > rc[t]["revised"] for t in TARGETS),
                         "per_game_full_minus_revised": tm.boot(pgd, np.abs(pgd.full - pgd.actual), np.abs(pgd.revised - pgd.actual), key="key"),
                         "per_game_by_season": per_season(pgd, "full", "revised", "actual")},
        "P4_drafts": {"beats_naive": sum(out["drafts"][t]["full"] > out["drafts"][t]["naive"] for t in TARGETS),
                      "beats_original": sum(out["drafts"][t]["full"] > out["drafts"][t]["original"] for t in TARGETS)},
    }
    res["P1_full_vs_naive_rank"]["pass"] = res["P1_full_vs_naive_rank"]["seasons_better"] >= 4
    res["P2_full_vs_original_rank"]["pass"] = res["P2_full_vs_original_rank"]["seasons_better"] >= 4
    ci = res["P3_additions"]["per_game_full_minus_revised"]["ci95"]
    res["P3_additions"]["pass"] = res["P3_additions"]["rank_seasons_better"] >= 3 and ci[1] < 0
    res["P4_drafts"]["pass"] = res["P4_drafts"]["beats_naive"] >= 3 and res["P4_drafts"]["beats_original"] >= 3
    return res


# ------------------------------------------------------------------ in season (P5-P7)
def season_rows(t, pg, tg, hist, draft, first_offset, min_before, max_before=None):
    prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
    g_all = pg[t].sort_values("GAME_DATE")
    h_prev = hist[(hist.season == prev)].set_index("PLAYER_ID")
    ages = nba_data.player_ages(prev).set_index("PLAYER_ID")["AGE"]
    last = pg[prev].groupby("PLAYER_ID")[["FGM", "FG3M", "FGA"]].sum()
    last = last[last.FGA >= ratings.SHOOTING_PRIOR_MIN_FGA]
    prior_efg = efg(last.FGM, last.FG3M, last.FGA).to_dict()
    before_seasons = bt.SEASONS[:bt.SEASONS.index(t)]
    base = bpv.rookie_baselines(bpv.rookie_seasons(before_seasons, {s: pg[s] for s in before_seasons}, draft,
                                                   hist[hist.season.isin(before_seasons)]))
    picks = draft.drop_duplicates("PERSON_ID", keep="last").set_index("PERSON_ID")["OVERALL_PICK"]
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)[t]
    cps = bt.checkpoints(g_all, first_offset)
    rows = []
    for pid, g in g_all.groupby("PLAYER_ID"):
        dates = g.GAME_DATE.tolist()
        fp, mins = g.FPTS.to_numpy(float), g.MIN.to_numpy(float)
        fgm, fg3m, fga = (np.cumsum(g[c].to_numpy(float)) for c in ("FGM", "FG3M", "FGA"))
        for c in cps:
            i = bisect_left(dates, c)
            if i < min_before or len(dates) - i < 10 or (max_before and i > max_before):
                continue
            S, mpg = fp[:i].mean(), mins[:i].mean()
            if mpg < 12:
                continue
            r = slice(max(0, i - 5), i)
            L5, m5 = fp[r].mean(), mins[r].mean()
            dm = S / max(mpg, 1) * (m5 - mpg)
            split = S + MIN_W * dm + EFF_W * (L5 - S - dm) if i >= 5 else S
            if pid in debuts:
                prior, k = base.get(bpv.pick_bucket(picks.get(pid)), base["undrafted"])["fpts_per_game"], ROOKIE_K
            elif pid in h_prev.index and h_prev.loc[pid, "played"] >= 20:
                prior = h_prev.loc[pid, "fpts_pg"] + (age_adj(ages, pid) if h_prev.loc[pid, "mpg"] >= 15 else 0.0)
                k = PRIOR_K
            else:
                prior, k = None, 0
            shrunk = bpv.shrink(split, i, prior, k) if prior is not None else split
            shrunk_s = bpv.shrink(S, i, prior, k) if prior is not None else S
            recal = RECAL[0] + RECAL[1] * shrunk if i >= 10 else shrunk
            before = g_all[g_all.GAME_DATE < c]
            league = efg(before.FGM.sum(), before.FG3M.sum(), before.FGA.sum())
            shoot = recal + (SHOOT * (efg(fgm[i - 1], fg3m[i - 1], fga[i - 1]) - prior_efg.get(pid, league)) * fga[i - 1] / i
                             if i >= 10 and fga[i - 1] > 0 else 0.0)
            rows.append({"season": t, "key": f"{pid}{t}", "n": i, "A": fp[i:].mean(), "season_avg": S,
                         "original": 0.8 * S + 0.2 * L5, "has_prior": prior is not None and pid not in debuts,
                         "prior_only": shrunk_s, "shrunk": shrunk, "recal": recal, "full": shoot})
    return rows


def in_season(pg, tg, hist, draft):
    rows, early = [], []
    for t in TARGETS:
        rows += season_rows(t, pg, tg, hist, draft, 28, 10)
        early += season_rows(t, pg, tg, hist, draft, 7, 1, max_before=20)
        print(t, "in-season rows", len(rows), len(early), flush=True)
    d, e = pd.DataFrame(rows), pd.DataFrame(early)
    e = e[e.has_prior]
    p5 = per_season(d, "full", "original", "A")
    b5 = tm.boot(d, np.abs(d.full - d.A), np.abs(d.original - d.A), key="key")
    p6r = per_season(d, "recal", "shrunk", "A")
    p6s = per_season(d, "full", "recal", "A")
    p7 = per_season(e, "prior_only", "season_avg", "A")
    return {
        "n_checkpoints": len(d), "n_early": len(e),
        "mae": {m: float(np.abs(d[m] - d.A).mean()) for m in ("season_avg", "original", "shrunk", "recal", "full")},
        "P5_full_vs_original": {"per_season": p5, "seasons_better": wins(p5), "pooled": b5,
                                "pass": wins(p5) >= 4 and b5["ci95"][1] < 0},
        "P6_recalibration": {"per_season": p6r, "seasons_better": wins(p6r), "pass": wins(p6r) >= 3},
        "P6_shooting_regression": {"per_season": p6s, "seasons_better": wins(p6s), "pass": wins(p6s) >= 3},
        "P7_early_prior": {"per_season": p7, "seasons_better": wins(p7), "pass": wins(p7) >= 4,
                           "mae": {m: float(np.abs(e[m] - e.A).mean()) for m in ("season_avg", "prior_only")}},
    }


# ------------------------------------------------------------------ availability (P8-P9)
def availability(pg, tg, hist, draft):
    p8 = {}
    for t in TARGETS:
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        ids = set(hist[(hist.season == prev) & (hist.mpg >= 20) & (hist.played >= 20)].PLAYER_ID)
        actual = hist[(hist.season == t) & hist.PLAYER_ID.isin(ids)].set_index("PLAYER_ID").availability
        p_league, _ = rb.league_before(hist, t)
        shrunk = bt.predict_availability(hist, t, 0.5, 123, p_league).reindex(actual.index)
        career = bt.predict_availability(hist, t, 1.0, 0, p_league).reindex(actual.index)
        p8[t] = bt.mae(shrunk, actual) - bt.mae(career, actual)
    rep = pd.DataFrame(columns=["season", "GAME_DATE", "PLAYER_ID", "Current Status", "category", "Reason"])
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    rows = []
    for t in TARGETS:
        rows += t3.rows_for(t, pg, tg, hist, rep, debuts[t])
    d = pd.DataFrame(rows)
    d["streak_adj"] = np.clip(d.p_w1 + STREAK[0] + STREAK[1] * d.streak.clip(upper=STREAK[2]), 0, 1)
    d["season"] = d.target
    p9 = per_season(d, "streak_adj", "p_w1", "availability", loss=np.square)
    return {"P8_shrunk_vs_career": {"per_season": p8, "seasons_better": wins(p8), "pass": wins(p8) >= 3},
            "P9_absence_streak": {"n": len(d), "per_season_squared": p9, "seasons_better": wins(p9), "pass": wins(p9) >= 3,
                                  "per_season_abs": per_season(d, "streak_adj", "p_w1", "availability")}}


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    res = {"preseason": preseason(pg, tg, hist)}
    res["in_season"] = in_season(pg, tg, hist, draft)
    res["availability"] = availability(pg, tg, hist, draft)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    for part in res.values():
        for k, v in part.items():
            if k[:1] == "P":
                print(k, "PASS" if v["pass"] else "FAIL", {x: y for x, y in v.items() if x in ("seasons_better", "rank_seasons_better", "beats_naive", "beats_original", "pooled", "per_game_full_minus_revised")})


if __name__ == "__main__":
    main()
