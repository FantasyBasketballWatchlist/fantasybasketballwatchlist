"""Round 7: shooting-efficiency regression (from box scores), verified on all weekly checkpoints.

Run:  python -m analysis.test_round7        (writes analysis/test_round7.json)

The tracking test (test_tracking_hustle.py) found that a term b x (eFG% to date - league eFG%) x FGA per
game improves rest-of-season projections, and that the shot-quality part added nothing. Here, with box
scores only:
E1  in season, every weekly checkpoint 2021-22..2025-26 (current method: split + recalibration)
E2  preseason: last season's (eFG% - league) x FGA added to last season + age + crowding
Leave-one-season-out; adoption rule: 95% interval excludes 0 AND better in most seasons.
"""
import json
import os
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp
from analysis import test_minutes_model as tmm
from analysis import test_misc as tm

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_round7.json")
RECAL = (2.964, 0.910)
SEASONS5 = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def efg(fgm, fg3m, fga):
    return (fgm + 0.5 * fg3m) / np.maximum(fga, 1)


def judge(d, new, old, target, key="key", season="season"):
    b = tm.boot(d, np.abs(d[new] - d[target]), np.abs(d[old] - d[target]), key=key)
    per = {s: float((np.abs(g[new] - g[target]) - np.abs(g[old] - g[target])).mean()) for s, g in d.groupby(season)}
    wins = sum(v < 0 for v in per.values())
    v = tm.verdict(b)
    return {"minus_current": b, "per_season": per, "seasons_better": wins,
            "verdict": "better" if v == "better" and wins > len(per) / 2 else ("tie" if v == "better" else v)}


def e1(pg):
    rows = []
    for s in SEASONS5:
        g_all = pg[s].sort_values("GAME_DATE")
        by_player = {pid: g for pid, g in g_all.groupby("PLAYER_ID")}
        for c in bt.checkpoints(g_all, 28):
            before = g_all[g_all.GAME_DATE < c]
            league = efg(before.FGM.sum(), before.FG3M.sum(), before.FGA.sum())
            st = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"),
                                                 fgm=("FGM", "sum"), fg3m=("FG3M", "sum"), fga=("FGA", "sum"))
            after_n = g_all[g_all.GAME_DATE >= c].groupby("PLAYER_ID").size()
            for pid, r in st[(st.n >= 10) & (st.mpg >= 12)].iterrows():
                if after_n.get(pid, 0) < 10:
                    continue
                g = by_player[pid]
                l5 = g[g.GAME_DATE < c].tail(5)
                pm = r.fp / max(r.mpg, 1)
                dm = pm * (l5.MIN.mean() - r.mpg)
                pred = RECAL[0] + RECAL[1] * (r.fp + 0.3 * dm + 0.1 * (l5.FPTS.mean() - r.fp - dm))
                rows.append({"season": s, "PLAYER_ID": pid, "pred": pred, "A": g[g.GAME_DATE >= c].FPTS.mean(),
                             "x": (efg(r.fgm, r.fg3m, r.fga) - league) * r.fga / r.n, "n": r.n})
    d = pd.DataFrame(rows)
    d["resid"] = d.A - d.pred
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    d["new"] = np.nan
    coefs = {}
    for s in SEASONS5:
        tr = d[d.season != s]
        b = float((tr.x * tr.resid).sum() / (tr.x ** 2).sum())
        coefs[s] = round(b, 3)
        m = d.season == s
        d.loc[m, "new"] = d.loc[m, "pred"] + b * d.loc[m, "x"]
    b_all = float((d.x * d.resid).sum() / (d.x ** 2).sum())
    return {"n": len(d), "coef_by_fold": coefs, "coef_all": b_all, "x_sd": float(d.x.std()),
            **judge(d, "new", "pred", "A")}


def e2(pg):
    tab = pp.season_table(pg)
    frames = {}
    for t in pp.TARGETS:
        f = pp.frame(tab, t)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        g = pg[prev]
        league = efg(g.FGM.sum(), g.FG3M.sum(), g.FGA.sum())
        agg = g.groupby("PLAYER_ID").agg(fgm=("FGM", "sum"), fg3m=("FG3M", "sum"), fga=("FGA", "sum"), n=("FGA", "size"))
        x = (efg(agg.fgm, agg.fg3m, agg.fga) - league) * agg.fga / agg.n
        f["x"] = f.PLAYER_ID.map(x).fillna(0)
        ctx = tmm.roster_context(pg, t)
        f["crowding"] = f.PLAYER_ID.map(ctx.crowding).fillna(0)
        frames[t] = f
    out = []
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        for d in (tr, te):
            d["last"] = d.fp1
        curve = pp.fit_age_curve(tr, "last")
        for d in (tr, te):
            d["base"] = pp.with_age(d, "last", curve) - 0.0177 * d.crowding
            d["resid"] = d.actual - d.base
        b = float((tr.x * tr.resid).sum() / (tr.x ** 2).sum())
        te["new"] = te.base + b * te.x
        te["coef"] = b
        te["season"] = t
        out.append(te)
    d = pd.concat(out, ignore_index=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    return {"n": len(d), "coefs": sorted(set(round(float(c), 3) for c in d.coef)), **judge(d, "new", "base", "actual")}


def main():
    pg, _ = bt.load()
    res = {"E2_preseason": e2(pg)}
    print("E2", json.dumps(res["E2_preseason"], default=float), flush=True)
    res["E1_in_season"] = e1(pg)
    print("E1", json.dumps(res["E1_in_season"], default=float), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
