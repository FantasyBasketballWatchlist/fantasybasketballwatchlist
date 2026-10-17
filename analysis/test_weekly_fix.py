"""Fixing the weekly value's injury-report gap.

Run:  python -m analysis.test_weekly_fix        (writes analysis/test_weekly_fix.json)

An injury report lists only teams playing that day, so taking the single latest report before a week
misses injured players whose teams didn't play that day (they look "not listed"). Candidates:
  A  team-aware lookup: each player's status comes from the latest report (up to 4 days back) that
     included his team's game
  B  "sat recently": his team played in the 3 days before the week and he didn't play
  A+B both
Baseline: the current method (single latest report). Weekly totals as in test_round3.p4; status
factors refit on the training seasons. Adoption rule: 95% interval excludes 0 AND better in the
majority of seasons (leave-one-season-out over 2021-22..2025-26).
"""
import datetime as dt
import json
import os
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_injury_reports as ti
from analysis import test_misc as tm

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_weekly_fix.json")


def status_key(stt, cat, ser):
    if stt == "Out":
        return "out_serious" if ser else f"out_{cat}"
    return stt.lower()


def rows(pg, tg, rep):
    out = []
    for s in ti.SEASONS:
        g_all = pg[s].sort_values("GAME_DATE")
        tgs = tg[s]
        rs = rep[rep.season == s].copy()
        rs["team_abbr"] = rs.Matchup.str.split("@")          # both teams in the matchup
        dates = sorted(rs.REPORT_DATE.unique())
        abbr_of = g_all.drop_duplicates("TEAM_ID").set_index("TEAM_ID").TEAM_ABBREVIATION
        first = dt.date.fromisoformat(g_all.GAME_DATE.min())
        monday = first + dt.timedelta(days=(7 - first.weekday()) % 7 + 21)
        last = dt.date.fromisoformat(g_all.GAME_DATE.max())
        while monday + dt.timedelta(days=6) <= last:
            ws, we = monday.isoformat(), (monday + dt.timedelta(days=7)).isoformat()
            j = bisect_left(dates, ws) - 1
            single = rs[rs.REPORT_DATE == dates[j]] if j >= 0 else rs.iloc[0:0]
            single_status = {p: status_key(a, b, c) for p, a, b, c in
                             zip(single.PLAYER_ID, single["Current Status"], single.category, single.serious)}
            # Team-aware: latest report within 4 days before the week that lists each team's game.
            recent = rs[(rs.REPORT_DATE < ws) & (rs.REPORT_DATE >= (monday - dt.timedelta(days=4)).isoformat())]
            team_latest = {}
            for rd, grp in recent.groupby("REPORT_DATE"):
                for teams in grp.team_abbr:
                    for t in teams:
                        team_latest[t] = max(team_latest.get(t, ""), rd)
            aware = {}
            for rd, grp in recent.groupby("REPORT_DATE"):
                for p, a, b, c, team in zip(grp.PLAYER_ID, grp["Current Status"], grp.category, grp.serious, grp.Team):
                    aware[(p, rd)] = status_key(a, b, c)
            before = g_all[g_all.GAME_DATE < ws]
            week = g_all[(g_all.GAME_DATE >= ws) & (g_all.GAME_DATE < we)]
            last3 = (monday - dt.timedelta(days=3)).isoformat()
            team_recent = set(tgs[(tgs.GAME_DATE >= last3) & (tgs.GAME_DATE < ws)].TEAM_ID)
            played_recent = set(g_all[(g_all.GAME_DATE >= last3) & (g_all.GAME_DATE < ws)].PLAYER_ID)
            team_before = tgs[tgs.GAME_DATE < ws].groupby("TEAM_ID").size()
            team_week = tgs[(tgs.GAME_DATE >= ws) & (tgs.GAME_DATE < we)].groupby("TEAM_ID").size()
            st = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"), team=("TEAM_ID", "last"))
            actual = week.groupby("PLAYER_ID").FPTS.sum()
            for pid, r in st[(st.mpg >= 20) & (st.n >= 10)].iterrows():
                gw = team_week.get(r.team, 0)
                if gw == 0:
                    continue
                abbr = abbr_of.get(r.team)
                rd = team_latest.get(abbr)
                out.append({"season": s, "PLAYER_ID": pid, "fp": r.fp, "games": gw,
                            "share": min(r.n / team_before.get(r.team, r.n), 1.0),
                            "status_single": single_status.get(pid, "not_listed"),
                            "status_aware": aware.get((pid, rd), "not_listed") if rd else "not_listed",
                            "sat": (r.team in team_recent) and (pid not in played_recent),
                            "actual": actual.get(pid, 0.0)})
            monday += dt.timedelta(days=7)
    return pd.DataFrame(out)


def main():
    pg, tg = bt.load()
    rep, _ = ti.load_reports(pg)
    d = rows(pg, tg, rep)
    d["base0"] = d.fp * d.games * d.share
    variants = {"current": ("status_single", False), "A_team_aware": ("status_aware", False),
                "B_sat_recently": ("status_single", True), "A+B": ("status_aware", True)}
    preds = {k: pd.Series(np.nan, index=d.index) for k in variants}
    for s in d.season.unique():
        tr, te = d[d.season != s], d[d.season == s]
        for name, (col, use_sat) in variants.items():
            grp = tr[col] + (("|sat" if use_sat else "") + tr.sat.map({True: "1", False: "0"}) if use_sat else "")
            ratio = tr.actual.groupby(grp).sum() / tr.base0.groupby(grp).sum()
            gte = te[col] + (("|sat" if use_sat else "") + te.sat.map({True: "1", False: "0"}) if use_sat else "")
            preds[name].loc[te.index] = te.base0 * gte.map(ratio).fillna(1.0)
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    res = {"n": len(d), "share_sat": float(d.sat.mean()),
           "share_listed_single": float((d.status_single != "not_listed").mean()),
           "share_listed_team_aware": float((d.status_aware != "not_listed").mean()),
           "mae": {k: bt.mae(v, d.actual) for k, v in preds.items()}}
    for name in ("A_team_aware", "B_sat_recently", "A+B"):
        b = tm.boot(d, np.abs(preds[name] - d.actual), np.abs(preds["current"] - d.actual), key="key")
        per = {s: float((np.abs(preds[name] - d.actual) - np.abs(preds["current"] - d.actual))[d.season == s].mean())
               for s in d.season.unique()}
        wins = sum(v < 0 for v in per.values())
        res[name] = {"minus_current": b, "per_season": per, "seasons_better": wins,
                     "verdict": "better" if tm.verdict(b) == "better" and wins > len(per) / 2 else tm.verdict(b)}
    b = tm.boot(d, np.abs(preds["A+B"] - d.actual), np.abs(preds["A_team_aware"] - d.actual), key="key")
    res["A+B_minus_A"] = b
    fit_all = {}
    for name, (col, use_sat) in variants.items():
        grp = d[col] + (("|sat" + d.sat.map({True: "1", False: "0"})) if use_sat else "")
        fit_all[name] = (d.actual.groupby(grp).sum() / d.base0.groupby(grp).sum()).round(3).to_dict()
    res["factors_all_seasons"] = fit_all
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(json.dumps({k: v for k, v in res.items() if k != "factors_all_seasons"}, indent=1, default=float))


if __name__ == "__main__":
    main()
