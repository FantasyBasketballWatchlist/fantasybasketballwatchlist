"""Teammate absences in BPV's in-season production (rules: docs/prereg-bpv-market-minutes.md, "Addendum").

    python -m analysis.bpv_teammates            (writes analysis/bpv_teammates.json)
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import bpv   # noqa: E402
import nba_data   # noqa: E402
from analysis.bpv_market import DESIGN, MIN_ROS, ROOT, SEASON, TEST   # noqa: E402
from analysis.bpv_replay import ratings_on   # noqa: E402

A_GRID = [0, 0.25, 0.5, 0.75, 1.0]
ROTATION_MPG = 20
OUT = os.path.join(ROOT, "analysis", "bpv_teammates.json")


def main():
    games = bpv.add_fpts(nba_data.player_game_logs(SEASON))
    games = games[games["MIN"] > 0]
    rows = []
    for day in DESIGN + TEST:
        players, _ = ratings_on(SEASON, day)
        cut = day.isoformat()
        before, after = games[games["GAME_DATE"] < cut], games[games["GAME_DATE"] >= cut]
        mpg = before.groupby("PLAYER_ID")["MIN"].mean()
        ros = after.groupby("PLAYER_ID")["FPTS"].agg(["mean", "size", "sum"])
        p = players.assign(mpg=players["id"].map(mpg)).dropna(subset=["mpg"])
        out = p[(p["report_status"] == "Out") & (p["mpg"] >= ROTATION_MPG)]
        vac = (out["mpg"] * (1 - out["availability"])).groupby(out["team"]).sum()
        active = p[p["report_status"] != "Out"]
        act_sum = active.groupby("team")["mpg"].sum()
        for r in active.itertuples():
            v = float(vac.get(r.team, 0.0))
            share = float(r.mpg / act_sum[r.team]) if act_sum.get(r.team, 0) > 0 else 0.0
            pid = int(r.id)
            rows.append({"date": cut, "id": pid, "prod": float(r.production), "avail": float(r.availability), "mpg": float(r.mpg),
                         "V": v, "share": share,
                         "ros_fpg": float(ros.loc[pid, "mean"]) if pid in ros.index else np.nan,
                         "ros_games": int(ros.loc[pid, "size"]) if pid in ros.index else 0,
                         "ros_total": float(ros.loc[pid, "sum"]) if pid in ros.index else 0.0})
        print(f"{cut}: {len(out)} rotation players Out, {sum(r['date'] == cut for r in rows)} active players", flush=True)
    d = pd.DataFrame(rows)

    def produce(x, a):
        return x["prod"] * (1 + a * x["V"] * x["share"] / x["mpg"].clip(lower=1))

    def mae(x, a):
        e = x[x["ros_games"] >= MIN_ROS]
        return float((produce(e, a) - e["ros_fpg"]).abs().mean())

    des, test = d[d["date"] < "2025-01-01"], d[d["date"] >= "2025-01-01"]
    grid = {str(a): mae(des, a) for a in A_GRID}
    a_best = min(A_GRID, key=lambda a: mae(des, a))
    if mae(des, a_best) >= mae(des, 0) - 1e-9:
        a_best = 0
    per_date, better = {}, 0
    for day, x in test.groupby("date"):
        cur, new = mae(x, 0), mae(x, a_best)
        per_date[day] = {"current": cur, "new": new}
        better += new < cur
    affected = test[test["V"] > 0]
    rc = lambda x, a: float((produce(x, a) * x["avail"]).rank().corr(x["ros_total"].rank()))
    res = {"rules": "docs/prereg-bpv-market-minutes.md (Addendum)", "alpha": a_best, "design_grid": grid,
           "test": {"current": mae(test, 0), "new": mae(test, a_best), "per_date": per_date, "dates_better": int(better),
                    "affected_players": int((affected["ros_games"] >= MIN_ROS).sum()),
                    "affected_current": mae(affected, 0) if len(affected) else None, "affected_new": mae(affected, a_best) if len(affected) else None,
                    "rank_corr_current": rc(test, 0), "rank_corr_new": rc(test, a_best)}}
    res["passes"] = bool(res["test"]["new"] < res["test"]["current"] and better >= 3)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
