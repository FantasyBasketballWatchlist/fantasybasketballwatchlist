"""Backtest of the single-game projections on 2025-26 (rules: docs/prereg-game-projections.md, "Backtest").

For every game day from the 15th on, project each player who played that day from the games before it only, then
score with game_projections.score. One change from the live model: the fantasy-point anchor is the season-to-date
average shrunk toward last season (8 pseudo-games), not BPV recomputed for every date.

    python -m analysis.game_backtest            (writes analysis/game_backtest.json)
"""
import json
import os
import time
import warnings

import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import game_projections as gp   # noqa: E402
import nba_data   # noqa: E402

SEASON, PRIOR_SEASON = "2025-26", "2024-25"
FIRST_DAY_INDEX = 14            # skip the first 14 game days
ANCHOR_K = 8
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_backtest.json")


def main():
    t0 = time.time()
    this_all = gp.with_combos(nba_data.player_game_logs(SEASON))
    last = gp.with_combos(nba_data.player_game_logs(PRIOR_SEASON))
    teams = nba_data.team_game_logs(SEASON)
    curves = gp.variance_curves(last)
    last_avg = last.groupby("PLAYER_ID")["FPTS"].mean()
    days = sorted(this_all["GAME_DATE"].unique())
    from analysis.game_fix2 import teammate_news
    news = teammate_news(SEASON)
    records = []
    for day in days[FIRST_DAY_INDEX:]:
        before = this_all[this_all["GAME_DATE"] < day]
        today_games = this_all[(this_all["GAME_DATE"] == day)]
        # Schedule for the day from the box scores: home team = "vs." in MATCHUP.
        tday = teams[teams["GAME_DATE"] == day]
        sched = pd.DataFrame({"GAME_DATE": day, "TEAM_ABBREVIATION": tday["TEAM_ABBREVIATION"],
                              "OPPONENT": tday["MATCHUP"].str[-3:], "HOME": tday["MATCHUP"].str.contains("vs.")})
        cur = before.groupby("PLAYER_ID")["FPTS"].agg(["mean", "size"])
        players = today_games.drop_duplicates("PLAYER_ID")[["PLAYER_ID", "PLAYER_NAME", "TEAM_ABBREVIATION"]]
        anchor = []
        for pid in players["PLAYER_ID"]:
            n = int(cur.at[pid, "size"]) if pid in cur.index else 0
            m = float(cur.at[pid, "mean"]) if n else None
            prior = float(last_avg[pid]) if pid in last_avg.index else m
            anchor.append(None if m is None and prior is None else ((n * m + ANCHOR_K * prior) / (n + ANCHOR_K) if n else prior))
        players = pd.DataFrame({"id": players["PLAYER_ID"].values, "name": players["PLAYER_NAME"].values,
                                "team": players["TEAM_ABBREVIATION"].values, "production": anchor, "report_status": None})
        hist = gp.last_games(before, last)
        tb = teams[teams["GAME_DATE"] < day]
        opp = gp.opponent_relative(before, tb)
        yday = (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        bench = gp.benchmark(before, last)
        nd = news[news["date"] == day]
        rows = gp.project_day(players, hist, curves, sched, day, opp, {}, {}, set(tb[tb["GAME_DATE"] == yday]["TEAM_ABBREVIATION"]), bench,
                              dict(zip(nd["id"], zip(nd["V"], nd["share"]))))
        records += [gp.flatten(day, r, bench.get(r["id"])) for r in rows]
    log = pd.DataFrame(records)
    res = gp.score(log, this_all)
    res.update({"rules": "docs/prereg-game-projections.md", "season": SEASON, "seconds": round(time.time() - t0)})
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    st = res["stats"]
    print(f"{res['player_games']} player-games over {res['game_days']} days")
    for s in gp.SHOWN:
        x = st[s]
        line = x.get("lines", {})
        print(f"{s:5} MAE {x['mae']:.2f} vs bench {x['mae_bench']:.2f} | inside 10-90: {x['inside_80']:.1%} | "
              f"Brier {line.get('brier', float('nan')):.4f} vs 0.5: {line.get('brier_50', float('nan')):.4f} | "
              + " ".join(f"{b['from']:.2f}:{b['predicted']:.2f}/{b['actual']:.2f}({b['n']})" for b in line.get("buckets", [])))
    print("passes:", res["passes"])


if __name__ == "__main__":
    main()
