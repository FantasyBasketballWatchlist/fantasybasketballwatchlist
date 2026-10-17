"""Round 6: the 65-game award threshold (2023-24 on).

Run:  python -m analysis.test_round6        (writes analysis/test_round6.json)

Since 2023-24 players need 65 games for MVP/All-NBA and other awards. Do award-level players (top 30 by
FPTS/game two weeks before the fantasy playoffs) who can still reach 65 but need most of their remaining
games play a larger share of the fantasy-playoff window than the tanking/status model expects?
Compared with the current expected-playoff-games model (share change by team status and age,
fitted leave-one-season-out). Adoption rule: 95% interval excludes 0 AND better in most seasons.
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_misc as tm
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_round6.json")


def main():
    rows = []
    pg, tg = bt.load()
    for s in ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]:
        t = tg[s]
        start, _ = bpv.playoff_window(t.GAME_DATE.max())
        cut = (dt.date.fromisoformat(start) - dt.timedelta(days=14)).isoformat()
        rec = t[t.GAME_DATE < cut].groupby("TEAM_ID").WL.apply(lambda x: (x == "W").mean())
        status = pd.Series("middle", index=rec.index)
        status[rec <= 0.35] = "bad"
        status[rec >= 0.68] = "top"
        g = pg[s]
        before = g[g.GAME_DATE < cut].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"),
                                                               mpg=("MIN", "mean"), team=("TEAM_ID", "last"))
        win_n = g[g.GAME_DATE >= start].groupby("PLAYER_ID").size()
        team_games = t[t.GAME_DATE >= start].groupby("TEAM_ID").size()
        team_before = t[t.GAME_DATE < cut].groupby("TEAM_ID").size()
        team_left_at_cut = t[t.GAME_DATE >= cut].groupby("TEAM_ID").size()
        ages = nba_data.player_ages(s).set_index("PLAYER_ID").AGE
        top30 = set(before[(before.mpg >= 20) & (before.n >= 30)].fp.nlargest(30).index)
        for pid, b in before[(before.mpg >= 20) & (before.n >= 30)].iterrows():
            need = 65 - b.n
            left = team_left_at_cut[b.team]
            chasing = s >= "2023-24" and pid in top30 and 0 < need <= left and need >= 0.6 * left
            rows.append({"season": s, "PLAYER_ID": pid,
                         "group": f"{status[b.team]}_{'vet' if ages.get(pid, 0) >= 28 else 'young'}",
                         "share": b.n / team_before[b.team], "share_w": win_n.get(pid, 0) / team_games[b.team],
                         "chasing": bool(chasing)})
    d = pd.DataFrame(rows)
    d["change"] = d.share_w - d.share
    out = []
    for s in d.season.unique():
        tr, te = d[d.season != s], d[d.season == s].copy()
        base_change = tr[~tr.chasing].groupby("group").change.mean()
        chase_extra = (tr[tr.chasing].change - tr[tr.chasing].group.map(base_change)).mean() if tr.chasing.any() else 0.0
        te["pred_base"] = (te.share + te.group.map(base_change)).clip(0, 1)
        te["pred_new"] = (te.share + te.group.map(base_change) + np.where(te.chasing, chase_extra, 0)).clip(0, 1)
        te["extra"] = chase_extra
        out.append(te)
    t_ = pd.concat(out, ignore_index=True)
    t_["key"] = t_.PLAYER_ID.astype(str) + t_.season
    chase = t_[t_.chasing].reset_index(drop=True)
    res = {"n": len(t_), "n_chasing": len(chase), "chasing_by_season": chase.season.value_counts().to_dict(),
           "fitted_extra_share_by_fold": sorted(set(round(float(x), 3) for x in t_.extra)),
           "chasing_mean_change": float(chase.change.mean()) if len(chase) else None,
           "non_chasing_top30_mean_change": None}
    if len(chase) >= 10:
        b = tm.boot(chase, np.abs(chase.pred_new - chase.share_w), np.abs(chase.pred_base - chase.share_w))
        per = {s: float((np.abs(g.pred_new - g.share_w) - np.abs(g.pred_base - g.share_w)).mean()) for s, g in chase.groupby("season")}
        res.update({"chasing_players": b, "per_season": per, "verdict": tm.verdict(b)})
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
