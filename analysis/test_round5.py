"""Round 5 candidates, each scored against current BPV out of sample.

Run:  python -m analysis.test_round5        (writes analysis/test_round5.json)

Adoption rule (set before testing): 95% interval (resampling players) excludes 0 in favor AND better in
the majority of individual held-out seasons (leave-one-season-out).

Q1  Returning teammate: a 20+ mpg teammate came back (in the team's last 5 games) from a 10+ game
    absence. Do his teammates' rest-of-season FPTS/game fall below the current projection?
Q2  Mid-season trades: players whose team changed within their last 10 games before a checkpoint;
    does a crowding term for the new team (vs the old) improve their rest-of-season projection?
Q3  Weekly opponents and home games: does opponents' fantasy points allowed (to date) or the number of
    home games this week improve weekly totals beyond the current weekly method?
Q4  Second-year jump and draft pedigree (preseason): beyond the age curve, do players entering their
    2nd/3rd season, or high draft picks in early seasons, improve more?
Q5  Second-half weighting (preseason): does last season's second half (after the midpoint of his
    games) predict next season better than the full-season average?
"""
import datetime as dt
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
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_round5.json")
CROWDING_COEF = -0.0177
RECAL = (2.964, 0.910)
SEASONS5 = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]


def judge(d, new, old, target, key):
    b = tm.boot(d, np.abs(d[new] - d[target]), np.abs(d[old] - d[target]), key=key)
    per = {s: float((np.abs(g[new] - g[target]) - np.abs(g[old] - g[target])).mean()) for s, g in d.groupby("season")}
    wins = sum(v < 0 for v in per.values())
    v = tm.verdict(b)
    return {"minus_current": b, "per_season": per, "seasons_better": wins,
            "verdict": "better" if v == "better" and wins > len(per) / 2 else ("tie" if v == "better" else v)}


def lofo_fit(d, xcols, resid_col="resid"):
    """Leave-one-season-out least squares of the residual on x; returns the out-of-fold adjustment."""
    adj = pd.Series(0.0, index=d.index)
    coefs = {}
    for s in d.season.unique():
        tr = d[d.season != s]
        X = tr[xcols].to_numpy()
        if not np.any(X):
            continue
        c, *_ = np.linalg.lstsq(X, tr[resid_col].to_numpy(), rcond=None)
        adj[d.season == s] = d.loc[d.season == s, xcols].to_numpy() @ c
        coefs[s] = [round(float(x), 4) for x in c]
    return adj, coefs


def checkpoint_rows(pg, tg):
    """Weekly checkpoints (as in backtest) with team context: returning teammates and recent trades."""
    rows = []
    for s in SEASONS5:
        g_all = pg[s].sort_values("GAME_DATE")
        sched = {t: sorted(x) for t, x in tg[s].groupby("TEAM_ID").GAME_DATE}
        by_player = {pid: g for pid, g in g_all.groupby("PLAYER_ID")}
        for c in bt.checkpoints(g_all, 28):
            before = g_all[g_all.GAME_DATE < c]
            after = g_all[g_all.GAME_DATE >= c]
            st = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"),
                                                 team=("TEAM_ID", "last"))
            after_n = after.groupby("PLAYER_ID").size()
            team_rot = st[st.mpg >= 10].groupby("team").mpg.sum()
            # Returning teammates: 20+ mpg before a 10+ game absence that ended within the team's last 5 games.
            returned = {}
            for pid, r in st[(st.mpg >= 20) & (st.n >= 10)].iterrows():
                g = by_player[pid]
                dates = g[g.GAME_DATE < c].GAME_DATE.tolist()
                sch = sched[r.team]
                j = bisect_left(sch, c)
                last5 = set(sch[max(0, j - 5):j])
                for d1, d2 in zip(dates, dates[1:]):
                    gap = bisect_left(sch, d2) - bisect_left(sch, d1) - 1
                    if gap >= 10 and d2 in last5:
                        returned[r.team] = returned.get(r.team, 0.0) + r.mpg
                        break
            for pid, r in st[(st.n >= 10) & (st.mpg >= 12)].iterrows():
                if after_n.get(pid, 0) < 10:
                    continue
                g = by_player[pid]
                prior = g[g.GAME_DATE < c]
                l5 = prior.tail(5)
                pm = r.fp / max(r.mpg, 1)
                dm = pm * (l5.MIN.mean() - r.mpg)
                pred = RECAL[0] + RECAL[1] * (r.fp + 0.3 * dm + 0.1 * (l5.FPTS.mean() - r.fp - dm))
                teams = prior.TEAM_ID.tolist()
                traded = len(set(teams[-10:])) > 1
                old_team = teams[0] if traded else r.team
                rows.append({"season": s, "PLAYER_ID": pid, "pred": pred, "A": g[g.GAME_DATE >= c].FPTS.mean(),
                             "returned": 0.0 if pid in () else returned.get(r.team, 0.0) * (0 if returned.get(r.team) is None else 1),
                             "self_returned": 0,
                             "traded": traded, "fpm": pm,
                             "crowd_change": (team_rot.get(r.team, 0) - team_rot.get(old_team, 0)) if traded else 0.0})
    d = pd.DataFrame(rows)
    d["resid"] = d.A - d.pred
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    return d


def q1_q2(pg, tg):
    d = checkpoint_rows(pg, tg)
    res = {"n": len(d)}
    d["x_ret"] = d.returned * d.fpm
    adj, coefs = lofo_fit(d, ["x_ret"])
    d["new_q1"] = d.pred + adj
    aff = d[d.returned > 0].reset_index(drop=True)
    res["Q1"] = {"coefs": coefs, "n_affected": len(aff), "mean_resid_affected": float(aff.resid.mean()),
                 **judge(d, "new_q1", "pred", "A", "key"), "affected_only": judge(aff, "new_q1", "pred", "A", "key")}
    d["x_trade"] = d.crowd_change * d.traded
    adj, coefs = lofo_fit(d, ["x_trade"])
    d["new_q2"] = d.pred + adj
    tr = d[d.traded].reset_index(drop=True)
    res["Q2"] = {"coefs": coefs, "n_traded_rows": len(tr), "mean_resid_traded": float(tr.resid.mean()),
                 **judge(d, "new_q2", "pred", "A", "key"), "traded_only": judge(tr, "new_q2", "pred", "A", "key")}
    return res


def q3(pg, tg):
    rows = []
    for s in SEASONS5:
        g_all = pg[s].sort_values("GAME_DATE")
        tgs = tg[s].copy()
        tgs["opp"] = tgs.MATCHUP.str[-3:]
        tgs["home"] = tgs.MATCHUP.str.contains(" vs. ")
        first = dt.date.fromisoformat(g_all.GAME_DATE.min())
        monday = first + dt.timedelta(days=(7 - first.weekday()) % 7 + 21)
        last = dt.date.fromisoformat(g_all.GAME_DATE.max())
        abbr = g_all.drop_duplicates("TEAM_ID").set_index("TEAM_ID").TEAM_ABBREVIATION
        while monday + dt.timedelta(days=6) <= last:
            ws, we = monday.isoformat(), (monday + dt.timedelta(days=7)).isoformat()
            before = g_all[g_all.GAME_DATE < ws]
            # Fantasy points allowed per game by each team (by opponents' players), to date, relative to league.
            opp_of = tgs.set_index(["GAME_ID", "TEAM_ID"]).opp
            bg = before.merge(tgs[["GAME_ID", "TEAM_ID", "opp"]], on=["GAME_ID", "TEAM_ID"])
            allowed = bg.groupby(["opp", "GAME_ID"]).FPTS.sum().groupby("opp").mean()
            allowed = allowed / allowed.mean()
            week = tgs[(tgs.GAME_DATE >= ws) & (tgs.GAME_DATE < we)]
            wk = week.groupby("TEAM_ID").agg(games=("GAME_ID", "size"), home=("home", "sum"),
                                             opp_strength=("opp", lambda o: float(np.mean([allowed.get(x, 1.0) for x in o]))))
            team_before = tgs[tgs.GAME_DATE < ws].groupby("TEAM_ID").size()
            st = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"), team=("TEAM_ID", "last"))
            actual = g_all[(g_all.GAME_DATE >= ws) & (g_all.GAME_DATE < we)].groupby("PLAYER_ID").FPTS.sum()
            for pid, r in st[(st.mpg >= 20) & (st.n >= 10)].iterrows():
                if r.team not in wk.index:
                    continue
                w = wk.loc[r.team]
                share = min(r.n / team_before.get(r.team, r.n), 1.0)
                rows.append({"season": s, "PLAYER_ID": pid, "base": r.fp * w.games * share, "games": w.games,
                             "home_share": w.home / w.games, "opp": w.opp_strength - 1, "actual": actual.get(pid, 0.0)})
            monday += dt.timedelta(days=7)
    d = pd.DataFrame(rows)
    d["resid"] = d.actual - d.base
    d["x_opp"] = d.base * d.opp
    d["x_home"] = d.base * (d.home_share - 0.5)
    d["key"] = d.PLAYER_ID.astype(str) + d.season
    out = {"n": len(d)}
    for name, cols in [("opponent", ["x_opp"]), ("home", ["x_home"]), ("both", ["x_opp", "x_home"])]:
        adj, coefs = lofo_fit(d, cols)
        d[f"new_{name}"] = d.base + adj
        out[name] = {"coefs": coefs, **judge(d, f"new_{name}", "base", "actual", "key")}
    return out


def q4_q5(pg):
    tab = pp.season_table(pg)
    draft = nba_data.draft_history().drop_duplicates("PERSON_ID", keep="last")
    picks = draft.set_index("PERSON_ID").OVERALL_PICK
    first_season = {}
    for s in bt.SEASONS:
        for pid in pg[s].PLAYER_ID.unique():
            first_season.setdefault(pid, s)
    frames = {}
    for t in pp.TARGETS:
        f = pp.frame(tab, t)
        ctx = tmm.roster_context(pg, t)
        f["crowding"] = f.PLAYER_ID.map(ctx.crowding).fillna(0)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        # Seasons of experience (only reliable for players drafted 2019+, i.e. first seen 2019-20 or later
        # and drafted that year); others are treated as veterans.
        drafted_year = draft.set_index("PERSON_ID").SEASON.astype(int)
        exp = []
        for pid in f.PLAYER_ID:
            dy = drafted_year.get(pid)
            exp.append((nba_data.season_start_year(t) - dy) if dy is not None and dy >= 2019 else 9)
        f["exp"] = exp
        f["second_year"] = (f.exp == 1).astype(float)
        f["third_year"] = (f.exp == 2).astype(float)
        pk = f.PLAYER_ID.map(picks)
        f["young_top10"] = ((f.exp <= 2) & (pk <= 10)).astype(float)
        g = pg[prev].sort_values("GAME_DATE")
        halves = []
        for pid, gg in g.groupby("PLAYER_ID"):
            n = len(gg)
            halves.append((pid, gg.FPTS.iloc[n // 2:].mean()))
        f["second_half"] = f.PLAYER_ID.map(dict(halves))
        frames[t] = f
    scored = []
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        for d in (tr, te):
            d["last"] = d.fp1
        curve = pp.fit_age_curve(tr, "last")
        for d in (tr, te):
            d["base"] = pp.with_age(d, "last", curve) + CROWDING_COEF * d.crowding
            d["resid"] = d.actual - d.base
        for name, cols in [("experience", ["second_year", "third_year"]), ("pedigree", ["young_top10"])]:
            c, *_ = np.linalg.lstsq(tr[cols].to_numpy(), tr.resid.to_numpy(), rcond=None)
            te[f"new_{name}"] = te.base + te[cols].to_numpy() @ c
            te[f"coef_{name}"] = str([round(x, 3) for x in c])
        grid = np.round(np.arange(0, 1.01, 0.1), 1)
        w = min(grid, key=lambda w: bt.mae(tr.base + w * (tr.second_half - tr.fp1), tr.actual))
        te["new_second_half"] = te.base + w * (te.second_half - te.fp1)
        te["w_second_half"] = w
        te["season"] = t
        scored.append(te)
    d = pd.concat(scored, ignore_index=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    out = {"n": len(d), "second_year_n": int(d.second_year.sum()), "third_year_n": int(d.third_year.sum())}
    for name in ("experience", "pedigree", "second_half"):
        extra = {"weights": sorted(set(d.w_second_half))} if name == "second_half" else {"coefs": sorted(set(d[f"coef_{name}"]))}
        out[name] = {**extra, **judge(d, f"new_{name}", "base", "actual", "key")}
    young = d[d.exp <= 2].reset_index(drop=True)
    if len(young):
        out["experience_young_only"] = judge(young, "new_experience", "base", "actual", "key")
    return out


def main():
    pg, tg = bt.load()
    res = {"Q4_Q5": q4_q5(pg)}
    print("Q4/Q5", json.dumps(res["Q4_Q5"], default=float), flush=True)
    res["Q3"] = q3(pg, tg)
    print("Q3", json.dumps(res["Q3"], default=float), flush=True)
    res.update(q1_q2(pg, tg))
    print("Q1", json.dumps(res["Q1"], default=float), flush=True)
    print("Q2", json.dumps(res["Q2"], default=float), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
