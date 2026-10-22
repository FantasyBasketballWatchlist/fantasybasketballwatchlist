"""Sportsbook lines and recent minutes in BPV's in-season production (rules: docs/prereg-bpv-market-minutes.md).

    python -m analysis.bpv_market            (writes analysis/bpv_market.json)
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import bpv   # noqa: E402
import nba_data   # noqa: E402
from analysis.bpv_replay import ratings_on   # noqa: E402
from analysis.real_lines import key   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEASON = "2024-25"
DESIGN = [dt.date(2024, 12, 2) + dt.timedelta(weeks=i) for i in range(5)]
TEST = [dt.date(2025, 1, 6) + dt.timedelta(weeks=i) for i in range(4)]
W_GRID = [0, 0.25, 0.5, 0.75]
L_GRID = [0, 0.25, 0.5, 0.75, 1.0]
MIN_ROS = 10
OUT = os.path.join(ROOT, "analysis", "bpv_market.json")


def line_pra(games):
    """(GAME_DATE, PLAYER_ID) -> consensus PRA line, for player-games with all three lines."""
    lines = pd.read_csv(os.path.join(ROOT, "data", "lines", "history.csv"))
    lines = lines[lines["stat"].isin(["PTS", "REB", "AST"])]
    cnt = lines.groupby(["event_id", "game_date", "player", "stat", "line"])["bookmaker"].nunique().reset_index()
    cnt = cnt.sort_values(["bookmaker", "line"], ascending=[False, True]).drop_duplicates(["event_id", "player", "stat"])
    wide = cnt.pivot_table(index=["game_date", "player"], columns="stat", values="line").dropna().reset_index()
    wide["pra_line"] = wide["PTS"] + wide["REB"] + wide["AST"]
    wide["k"] = wide["player"].map(key)
    ids = games.drop_duplicates("PLAYER_ID").assign(k=lambda x: x["PLAYER_NAME"].map(key)).set_index("k")["PLAYER_ID"]
    wide["PLAYER_ID"] = wide["k"].map(ids)
    return wide.dropna(subset=["PLAYER_ID"]).set_index(["game_date", "PLAYER_ID"])["pra_line"]


def main():
    games = bpv.add_fpts(nba_data.player_game_logs(SEASON))
    games["PRA"] = games["PTS"] + games["REB"] + games["AST"]
    games = games[games["MIN"] > 0].sort_values(["GAME_DATE", "GAME_ID"])
    pra_line = line_pra(games)
    # kappa: actual PRA / line PRA over November-December player-games with lines.
    g_idx = games.set_index(["GAME_DATE", "PLAYER_ID"])
    nd = pra_line[pra_line.index.get_level_values(0) < "2025-01-01"]
    act = g_idx["PRA"].reindex(nd.index)
    kappa = float(act.sum() / nd[act.notna()].sum())

    rows = []
    for day in DESIGN + TEST:
        players, _ = ratings_on(SEASON, day)
        cut = day.isoformat()
        before, after = games[games["GAME_DATE"] < cut], games[games["GAME_DATE"] >= cut]
        ros = after.groupby("PLAYER_ID")["FPTS"].agg(["mean", "size", "sum"])
        seas = before.groupby("PLAYER_ID").agg(min_mean=("MIN", "mean"), pra=("PRA", "mean"), fpts=("FPTS", "mean"))
        ewm = {}
        for pid, g in before.groupby("PLAYER_ID"):
            m = g["MIN"].to_numpy(float)
            w = 0.5 ** (np.arange(len(m))[::-1] / 3)
            ewm[pid] = float((w * m).sum() / w.sum())
        lo = (day - dt.timedelta(days=14)).isoformat()
        win = pra_line[(pra_line.index.get_level_values(0) >= lo) & (pra_line.index.get_level_values(0) < cut)]
        mk = win.groupby(level=1).agg(["mean", "size"])
        for p in players.itertuples():
            pid = int(p.id)
            if pid not in seas.index:
                continue
            s = seas.loc[pid]
            rows.append({"date": cut, "id": pid, "name": p.name, "prod": float(p.production), "avail": float(p.availability),
                         "min_mean": float(s.min_mean), "min_ewm": ewm.get(pid, np.nan), "pra": float(s.pra), "fpts": float(s.fpts),
                         "mkt_pra": float(mk.loc[pid, "mean"]) * kappa if pid in mk.index and mk.loc[pid, "size"] >= 3 else np.nan,
                         "ros_fpg": float(ros.loc[pid, "mean"]) if pid in ros.index else np.nan,
                         "ros_games": int(ros.loc[pid, "size"]) if pid in ros.index else 0,
                         "ros_total": float(ros.loc[pid, "sum"]) if pid in ros.index else 0.0})
        print(f"{cut}: {sum(r['date'] == cut for r in rows)} players", flush=True)
    d = pd.DataFrame(rows)

    def produce(x, w, lam):
        p = x["prod"] * np.where(x["min_mean"] > 1, (w * x["min_ewm"] + (1 - w) * x["min_mean"]) / x["min_mean"], 1.0)
        ratio = np.where(x["pra"] > 1, x["fpts"] / x["pra"], 0.0)
        adj = np.where(x["mkt_pra"].notna(), lam * (x["mkt_pra"] - x["pra"]) * ratio, 0.0)
        return p + adj

    def mae(x, w, lam):
        e = x[x["ros_games"] >= MIN_ROS]
        return float((produce(e, w, lam) - e["ros_fpg"]).abs().mean())

    des = d[d["date"] < "2025-01-01"]
    base = mae(des, 0, 0)
    w_best = min(W_GRID, key=lambda w: mae(des, w, 0))
    if mae(des, w_best, 0) >= base - 1e-9:
        w_best = 0
    l_best = min(L_GRID, key=lambda lam: mae(des, w_best, lam))
    if mae(des, w_best, l_best) >= mae(des, w_best, 0) - 1e-9:
        l_best = 0
    test = d[d["date"] >= "2025-01-01"]
    per_date = {}
    better = 0
    for day, x in test.groupby("date"):
        cur, new = mae(x, 0, 0), mae(x, w_best, l_best)
        per_date[day] = {"current": cur, "new": new}
        better += new < cur
    mk = test[test["mkt_pra"].notna()]
    def rank_corr(x, w, lam):
        val = produce(x, w, lam) * x["avail"]
        return float(val.rank().corr(x["ros_total"].rank()))
    res = {"rules": "docs/prereg-bpv-market-minutes.md", "kappa": kappa, "chosen": {"w_recent_minutes": w_best, "lambda_market": l_best},
           "design": {"current": base, "after_R": mae(des, w_best, 0), "after_R_M": mae(des, w_best, l_best),
                      "grid_R": {str(w): mae(des, w, 0) for w in W_GRID}, "grid_M": {str(l): mae(des, w_best, l) for l in L_GRID}},
           "test": {"current": mae(test, 0, 0), "new": mae(test, w_best, l_best), "per_date": per_date, "dates_better": int(better),
                    "with_lines_current": mae(mk, 0, 0), "with_lines_new": mae(mk, w_best, l_best),
                    "rank_corr_current": rank_corr(test, 0, 0), "rank_corr_new": rank_corr(test, w_best, l_best)},
           "players": {"design": int(len(des)), "test": int(len(test)), "test_with_lines": int(len(mk))}}
    res["passes"] = bool(res["test"]["new"] < res["test"]["current"] and better >= 3)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
