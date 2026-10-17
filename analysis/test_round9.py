"""Round 9: refinements to existing BPV pieces.

Run:  python -m analysis.test_round9        (writes analysis/test_round9.json)

Adoption rule (set before testing): 95% interval (resampling players) excludes 0 in favor AND better in
the majority of individual held-out seasons.

W1  Early-season prior: blend early-season production with the preseason BPV + ESPN hybrid instead of
    last season (age-adjusted). Seasons with genuine ESPN preseason projections.
W2  Replacement-level rank: 100 / 130 / 160 in the BPV value, scored by drafts with one IR slot.
W3  Rookie early-season prior: draft-slot baseline adjusted for preseason minutes (as used before the
    season) vs the plain baseline.
W4  Smooth age curve: piecewise-linear in age (knots 22, 25, 28, 31, 34) vs the six age brackets.
"""
import json
import os
import random
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp
from analysis import test_espn_projections as tep
from analysis import test_minutes_model as tmm
from analysis import test_misc as tm
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_round9.json")
CROWDING_COEF = -0.0177
RANKS = (100, 130, 160, 190, 220)
AGE_CURVE = {"<=21": 2.11, "22-23": 0.28, "24-26": -0.26, "27-29": -1.63, "30-32": -2.53, "33+": -3.74}


def judge(d, new, old, target, key="key", season="season"):
    b = tm.boot(d, np.abs(d[new] - d[target]), np.abs(d[old] - d[target]), key=key)
    per = {s: float((np.abs(g[new] - g[target]) - np.abs(g[old] - g[target])).mean()) for s, g in d.groupby(season)}
    wins = sum(v < 0 for v in per.values())
    v = tm.verdict(b)
    return {"minus_current": b, "per_season": per, "seasons_better": wins,
            "verdict": "better" if v == "better" and wins > len(per) / 2 else ("tie" if v == "better" else v)}


def w1(pg, tg):
    names = tep.name_map(pg)
    rows = []
    for s, year in tep.ESPN_SEASONS.items():
        prev = bt.SEASONS[bt.SEASONS.index(s) - 1]
        g_prev = pg[prev].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"))
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID").AGE
        ctx = tmm.roster_context(pg, s)
        espn = tep.projections(year)
        espn["PLAYER_ID"] = espn.name.map(tep.key).map(names)
        espn = espn.dropna(subset=["PLAYER_ID"]).drop_duplicates("PLAYER_ID").set_index("PLAYER_ID").espn_fpg
        cp = bt.checkpoint_rows(s, pg[s], tg[s], first_offset_days=7, min_before=1, min_after=10)
        cp = cp[cp.n_before <= 20]
        for r in cp.itertuples():
            pid = r.PLAYER_ID
            if pid not in g_prev.index or g_prev.loc[pid].n < 20 or g_prev.loc[pid].mpg < 15 or pid not in espn.index:
                continue
            age_adj = AGE_CURVE[bpv.age_bucket(ages[pid])] if pid in ages.index else 0.0
            prior_old = g_prev.loc[pid].fp + age_adj
            bpv_pre = prior_old + CROWDING_COEF * ctx.crowding.get(pid, 0.0)
            prior_new = 0.625 * bpv_pre + 0.375 * espn[pid]
            rows.append({"season": s, "PLAYER_ID": pid, "n": r.n_before, "S": r.S, "A": r.A_ros,
                         "cur": bpv.shrink(r.S, r.n_before, prior_old, 8), "new": bpv.shrink(r.S, r.n_before, prior_new, 8)})
    d = pd.DataFrame(rows)
    n_missing = int(d[["cur", "new", "A"]].isna().any(axis=1).sum())
    d = d.dropna(subset=["cur", "new", "A"]).reset_index(drop=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    elite = d[d.cur >= d.groupby("season").cur.transform(lambda x: x.quantile(0.9))].reset_index(drop=True)
    return {"n": len(d), "n_dropped_missing": n_missing, **judge(d, "new", "cur", "A"),
            "elite_top10pct": judge(elite, "new", "cur", "A")}


def w2(pg, tg):
    """One BPV version at a time in the paper's standard five-strategy field; scored at the 130th-player level."""
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    field = ["M3 x career GP%", "M5 80/20 x career GP%", "BPV (replacement-level)", "BPV + age", "Last season total FPTS"]
    res = {}
    for target in pp.TARGETS:
        curve = bt.age_curve_before(pg, target)
        base, _ = bt.preseason_frame(pg, hist, target, 0.5, 123, league_p, league_q, age_curve=curve)
        res[target] = {}
        for rank in RANKS:
            df = base.copy()
            if rank != 130:
                alt, _ = bt.preseason_frame(pg, hist, target, 0.5, 123, league_p, league_q, replacement_rank=rank, age_curve=curve)
                df["BPV + age"] = alt["BPV + age"].reindex(df.index)
            sim = bt.simulate_drafts(df.dropna(subset=field), field, n_sims=2000, target="actual_managed")
            res[target][f"R{rank}"] = {"mean": sim["BPV + age"]["mean"],
                                       "se": sim["BPV + age"]["sd"] / np.sqrt(2000 * 2)}
    diff = {f"R{r}": {t: res[t][f"R{r}"]["mean"] - res[t]["R130"]["mean"] for t in res} for r in RANKS if r != 130}
    return {"by_season": res, "minus_R130": diff,
            "seasons_beating_R130": {k: sum(v > 0 for v in d.values()) for k, d in diff.items()},
            "average_minus_R130": {k: float(np.mean(list(d.values()))) for k, d in diff.items()}}


def w3(pg, tg):
    draft = nba_data.draft_history().drop_duplicates("PERSON_ID", keep="last")
    rows = []
    for s in ["2022-23", "2023-24", "2024-25", "2025-26"]:
        others = [x for x in ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"] if x != s]
        base_rows = []
        for o in others:
            year = nba_data.season_start_year(o)
            pr = nba_data.preseason_game_logs(o).groupby("PLAYER_ID").MIN.agg(["size", "mean"])
            g = pg[o].groupby("PLAYER_ID").FPTS.agg(["mean", "size"])
            for d_ in draft[draft.SEASON.astype(int) == year].itertuples():
                if d_.PERSON_ID in g.index and g.loc[d_.PERSON_ID, "size"] >= 10:
                    base_rows.append({"bucket": bpv.pick_bucket(d_.OVERALL_PICK), "fp": g.loc[d_.PERSON_ID, "mean"],
                                      "pre": pr.loc[d_.PERSON_ID, "mean"] if d_.PERSON_ID in pr.index and pr.loc[d_.PERSON_ID, "size"] >= 2 else np.nan})
        b = pd.DataFrame(base_rows)
        base, typical = b.groupby("bucket").fp.mean(), b.groupby("bucket").pre.mean()
        year = nba_data.season_start_year(s)
        pre_now = nba_data.preseason_game_logs(s).groupby("PLAYER_ID").MIN.agg(["size", "mean"])
        rookies = {d_.PERSON_ID: bpv.pick_bucket(d_.OVERALL_PICK) for d_ in draft[draft.SEASON.astype(int) == year].itertuples()}
        cp = bt.checkpoint_rows(s, pg[s], tg[s], first_offset_days=7, min_before=1, min_after=10)
        cp = cp[cp.n_before <= 20]
        for r in cp.itertuples():
            if r.PLAYER_ID not in rookies:
                continue
            bk = rookies[r.PLAYER_ID]
            prior = base.get(bk, base.min())
            adj = 0.31 * (pre_now.loc[r.PLAYER_ID, "mean"] - typical.get(bk, np.nan)) \
                if r.PLAYER_ID in pre_now.index and pre_now.loc[r.PLAYER_ID, "size"] >= 2 else 0.0
            adj = 0.0 if pd.isna(adj) else adj
            rows.append({"season": s, "PLAYER_ID": r.PLAYER_ID, "A": r.A_ros,
                         "cur": bpv.shrink(r.S, r.n_before, prior, 10), "new": bpv.shrink(r.S, r.n_before, prior + adj, 10)})
    d = pd.DataFrame(rows)
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    return {"n": len(d), **judge(d, "new", "cur", "A")}


def w4(pg):
    tab = pp.season_table(pg)
    frames = {t: pp.frame(tab, t) for t in pp.TARGETS}
    knots = [22, 25, 28, 31, 34]

    def basis(age):
        a = np.asarray(age, dtype=float)
        return np.column_stack([np.ones_like(a), a] + [np.clip(a - k, 0, None) for k in knots])
    out = []
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True).dropna(subset=["age"])
        te = frames[t].dropna(subset=["age"]).copy()
        tr["last"], te["last"] = tr.fp1, te.fp1
        curve = pp.fit_age_curve(tr, "last")
        te["cur"] = pp.with_age(te, "last", curve)
        coef, *_ = np.linalg.lstsq(basis(tr.age), (tr.actual - tr.fp1).to_numpy(), rcond=None)
        te["new"] = te.fp1 + basis(te.age) @ coef
        te["season"] = t
        out.append(te)
    d = pd.concat(out, ignore_index=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    return {"n": len(d), **judge(d, "new", "cur", "actual")}


def main():
    pg, tg = bt.load()
    res = {}
    try:
        res = json.load(open(OUT))
    except (OSError, ValueError):
        pass
    for key, fn in (("W4_smooth_age", lambda: w4(pg)), ("W3_rookie_prior", lambda: w3(pg, tg))):
        if key not in res:
            res[key] = fn()
    if "elite_top10pct" not in res.get("W1_hybrid_prior", {}):
        res["W1_hybrid_prior"] = w1(pg, tg)
    res["W2_replacement_rank"] = w2(pg, tg)
    print("W2", json.dumps(res["W2_replacement_rank"], default=float), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
