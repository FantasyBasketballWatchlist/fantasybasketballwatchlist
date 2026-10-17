"""Availability, round 3: rest-of-season availability during the season.

Run:  python -m analysis.test_availability3     (writes analysis/test_availability3.json)

Every two weeks from 3 weeks in until 3 weeks before the end (2021-22..2025-26), for players with
20+ minutes per game (this season, 5+ games) and 5+ team games left: predict the share of his team's
remaining games he plays. The app's estimate: recent seasons incl. this one so far (decay 0.5, 123
games of league average); if the latest injury report (within 3 days) lists him Out with an injury,
the injury-type share instead.
Candidates:
  C1 this season counted more heavily (x2, x3, x5)
  C2 ongoing absence: consecutive team games missed right before the checkpoint (players not covered
     by an Out/injury listing), linear and 3+ games
  C3 age
Same rule: 95% interval excludes 0 in favor AND better in most held-out seasons.
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import robustness as rb
from analysis import test_injury_reports as tir
from analysis import test_misc as tm
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_availability3.json")
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def rows_for(season, pg, tg, hist, rep, debuts):
    games, teams = pg[season], tg[season]
    p_league, _ = rb.league_before(hist, season)
    prior_hist = hist[hist.season.map(bt.SEASONS.index) < bt.SEASONS.index(season)]
    ages = nba_data.player_ages(bt.SEASONS[bt.SEASONS.index(season) - 1]).set_index("PLAYER_ID").AGE
    rep_s = rep[rep.season == season]
    start, end = dt.date.fromisoformat(teams.GAME_DATE.min()), dt.date.fromisoformat(teams.GAME_DATE.max())
    out = []
    c = start + dt.timedelta(days=21)
    while c <= end - dt.timedelta(days=21):
        cs = c.isoformat()
        g_b, t_b = games[games.GAME_DATE < cs], teams[teams.GAME_DATE < cs]
        now = bpv.season_availability(g_b, t_b, debuts)
        now["season"] = season
        h = pd.concat([prior_hist, now], ignore_index=True)
        base = {w: _weighted(h, season, w, p_league) for w in (1, 2, 3, 5)}
        now = now.set_index("PLAYER_ID")
        last = g_b.sort_values("GAME_DATE").groupby("PLAYER_ID").agg(team=("TEAM_ID", "last"), date=("GAME_DATE", "last"))
        sched = t_b.groupby("TEAM_ID").GAME_DATE.apply(sorted)
        left = teams[teams.GAME_DATE >= cs].groupby("TEAM_ID").size()
        played_after = games[games.GAME_DATE >= cs].groupby("PLAYER_ID").size()
        recent_rep = rep_s[(rep_s.GAME_DATE < cs) & (rep_s.GAME_DATE >= (c - dt.timedelta(days=3)).isoformat())]
        latest = recent_rep.sort_values("GAME_DATE").groupby("PLAYER_ID").last()
        for pid, r in now[(now.mpg >= 20) & (now.played >= 5)].iterrows():
            team = last.loc[pid, "team"]
            n_left = left.get(team, 0)
            if n_left < 5:
                continue
            streak = sum(d > last.loc[pid, "date"] for d in sched.get(team, []))
            share = None
            if pid in latest.index:
                lr = latest.loc[pid]
                kind = bpv.injury_type(lr.Reason)
                if lr["Current Status"] == "Out" and lr.category == "injury" and kind in ratings.REPORT_SHARE_PLAYED:
                    share = ratings.REPORT_SHARE_PLAYED[kind]
            status = latest.loc[pid, "Current Status"] if pid in latest.index else "none"
            cat = latest.loc[pid, "category"] if pid in latest.index else "none"
            pdates = g_b[g_b.PLAYER_ID == pid].GAME_DATE.sort_values().tolist()
            tdates = sched.get(team, [])
            recent_return = 0.0
            for d1, d2 in zip(pdates, pdates[1:]):
                if d2 >= (c - dt.timedelta(days=14)).isoformat() and sum(d1 < x < d2 for x in tdates) >= 5:
                    recent_return = 1.0
            row = {"status": status, "status_category": cat, "recent_return": recent_return}
            row.update({"target": season, "PLAYER_ID": pid, "checkpoint": cs,
                   "availability": min(1.0, played_after.get(pid, 0) / n_left),
                   "report_out": share is not None, "streak": min(streak, 20), "streak3": float(streak >= 3),
                   "age": ages.get(pid, np.nan)})
            for w, b in base.items():
                row[f"p_w{w}"] = share if share is not None else float(b.get(pid, p_league))
            out.append(row)
        c += dt.timedelta(days=14)
    return out


def _weighted(h, season, w, prior):
    """predict_availability with this season's games counted w times."""
    h = h.copy()
    m = h.season == season
    h.loc[m, "played"] *= w
    h.loc[m, "possible"] *= w
    return bpv.predict_availability(h, bt.SEASONS, season, 0.5, 123, prior)


def judge(d, new, old):
    d = d.reset_index(drop=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    out = {"n": len(d)}
    for name, loss in (("abs", np.abs), ("squared", np.square)):
        b = tm.boot(d, loss(d[new] - d.availability), loss(d[old] - d.availability), key="key")
        per = {s: float((loss(g[new] - g.availability) - loss(g[old] - g.availability)).mean()) for s, g in d.groupby("target")}
        wins = sum(v < 0 for v in per.values())
        v = tm.verdict(b)
        out[name] = {"minus_base": b, "per_season": per, "seasons_better": f"{wins}/{len(per)}",
                     "verdict": "better" if v == "better" and wins > len(per) / 2 else ("tie" if v == "better" else v)}
    return out


def correct(d, feats, base="p_w1"):
    d = d.dropna(subset=feats).copy()
    d["new"] = np.nan
    coefs = {}
    for t in d.target.unique():
        tr, m = d[d.target != t], d.target == t
        mu = tr[feats].mean()
        X1 = np.column_stack([np.ones(len(tr)), (tr[feats] - mu).to_numpy()])
        b, *_ = np.linalg.lstsq(X1, (tr.availability - tr[base]).to_numpy(), rcond=None)
        rec = (tr.availability - tr[base]).mean()
        d.loc[m, "new"] = np.clip(d.loc[m, base] + b[0] + (d.loc[m, feats] - mu).to_numpy() @ b[1:], 0, 1)
        d.loc[m, "recentered"] = np.clip(d.loc[m, base] + rec, 0, 1)
        coefs[t] = [round(float(x), 4) for x in b[1:]]
    return d, coefs


def build_rows():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    rep, _ = tir.load_reports(pg)
    rows = []
    for s in SEASONS:
        rows += rows_for(s, pg, tg, hist, rep, debuts[s])
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(nba_data.CACHE_DIR, "availability_in_season.csv"), index=False)
    return d


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    rep, _ = tir.load_reports(pg)
    rows = []
    for s in SEASONS:
        rows += rows_for(s, pg, tg, hist, rep, debuts[s])
        print(s, len(rows), flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(os.path.join(nba_data.CACHE_DIR, "availability_in_season.csv"), index=False)
    res = {"n": len(d), "report_out_rows": int(d.report_out.sum()),
           "mae_app": float(np.abs(d.p_w1 - d.availability).mean())}
    for w in (2, 3, 5):
        res[f"C1_this_season_x{w}"] = judge(d, f"p_w{w}", "p_w1")
    free = d[~d.report_out]
    for name, feats in (("C2_streak", ["streak"]), ("C2_streak_3plus", ["streak3"]), ("C3_age", ["age"])):
        s, coefs = correct(free, feats)
        res[name] = {"coefs": coefs, "vs_app": judge(s, "new", "p_w1"), "vs_recentered": judge(s, "new", "recentered")}
    s, _ = correct(free, ["streak"])
    res["recentering_alone"] = judge(s, "recentered", "p_w1")
    for k, v in res.items():
        if isinstance(v, dict):
            j = v.get("vs_app", v)
            print(k, "| abs", j["abs"]["verdict"], round(j["abs"]["minus_base"]["diff"], 5), j["abs"]["minus_base"]["ci95"],
                  j["abs"]["seasons_better"], "| sq", j["squared"]["verdict"], round(j["squared"]["minus_base"]["diff"], 5),
                  j["squared"]["seasons_better"], "| coefs", v.get("coefs"), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
