"""Round 4 (part): stat-specific roster crowding, scorekeeper generosity, forecast disagreement.

Run:  python -m analysis.test_round4        (writes analysis/test_round4.json)

Adoption rule (set before testing): 95% interval (resampling players) excludes 0 in favor AND better
in the majority of individual held-out seasons.

S1  Stat-specific crowding (preseason). Beyond total-minutes crowding, do new teammates' rebounds,
    assists and shot attempts (last season, players opening the season on the same team) predict the
    player's change? Features scale with the player's own share of that stat.
S2  Scorekeeper generosity. Arena assist rate = assists per made field goal in games at that arena
    (both teams), relative to what those teams do elsewhere; blocks per opponent 2-point attempt
    likewise. Is it persistent year to year? If so, does it help project players who change teams?
S3  Forecast disagreement. Does |ESPN - BPV| per game predict the size of the hybrid's error, so that
    likely ranges should be wider for players the two sources disagree on?
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp
from analysis import test_espn_totals as et
from analysis import test_minutes_model as tmm
from analysis import test_misc as tm
import bpv

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_round4.json")
CROWDING_COEF = -0.0177


def per_season_diff(d, new, old, target):
    return {s: float((np.abs(g[new] - g[target]) - np.abs(g[old] - g[target])).mean()) for s, g in d.groupby("target")}


def s1(pg):
    tab = pp.season_table(pg)
    frames = {}
    for t in pp.TARGETS:
        f = pp.frame(tab, t)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        ctx = tmm.roster_context(pg, t)
        g = pg[prev].groupby("PLAYER_ID").agg(reb=("REB", "mean"), ast=("AST", "mean"), fga=("FGA", "mean"),
                                              mpg=("MIN", "mean"))
        team = ctx.team
        contrib = g.reindex(team.index).fillna(0)
        contrib[g.reindex(team.index).mpg.fillna(0) < 10] = 0
        totals = contrib.groupby(team).sum()
        mean_tot = totals.mean()
        for stat in ("reb", "ast", "fga"):
            crowd = team.map(totals[stat]) - contrib[stat] - mean_tot[stat]
            own = g[stat].reindex(f.PLAYER_ID).values
            f[f"x_{stat}"] = crowd.reindex(f.PLAYER_ID).fillna(0).values * own / g[stat][g.mpg >= 15].mean()
        f["crowding"] = f.PLAYER_ID.map(ctx.crowding).fillna(0).values
        frames[t] = f
    cols = ["x_reb", "x_ast", "x_fga"]
    scored = []
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        for d in (tr, te):
            d["last"] = d.fp1
        curve = pp.fit_age_curve(tr, "last")
        for d in (tr, te):
            d["base"] = pp.with_age(d, "last", curve) + CROWDING_COEF * d.crowding
        coef, *_ = np.linalg.lstsq(tr[cols].to_numpy(), (tr.actual - tr.base).to_numpy(), rcond=None)
        te["new"] = te.base + te[cols].to_numpy() @ coef
        te["coef"] = str([round(c, 4) for c in coef])
        scored.append(te)
    d = pd.concat(scored, ignore_index=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    b = tm.boot(d, np.abs(d.new - d.actual), np.abs(d.base - d.actual), key="key")
    per = per_season_diff(d, "new", "base", "actual")
    return {"n": len(d), "coefs_by_fold": sorted(set(d.coef)), "minus_current": b, "per_season": per,
            "verdict": tm.verdict(b) if (tm.verdict(b) != "better" or sum(v < 0 for v in per.values()) > len(per) / 2) else "better"}


def arena_rates(tg_s):
    g = tg_s.copy()
    g["home"] = g.MATCHUP.str.contains(" vs. ")
    games = g.groupby("GAME_ID").agg(ast=("AST", "sum"), fgm=("FGM", "sum"), blk=("BLK", "sum"),
                                     fga=("FGA", "sum"), fg3a=("FG3A", "sum"))
    home_team = g[g.home].set_index("GAME_ID").TEAM_ID
    games["arena"] = home_team.reindex(games.index)
    games["ast_rate"] = games.ast / games.fgm
    games["blk_rate"] = games.blk / (games.fga - games.fg3a)
    # Teams' own tendency: their games' rates wherever played; arena effect = home-game rate minus the
    # average of the two teams' all-game rates.
    team_games = g[["GAME_ID", "TEAM_ID"]].merge(games[["ast_rate", "blk_rate"]], left_on="GAME_ID", right_index=True)
    team_rate = team_games.groupby("TEAM_ID")[["ast_rate", "blk_rate"]].mean()
    pair = g.groupby("GAME_ID").TEAM_ID.apply(list)
    exp = pair.apply(lambda ts: team_rate.loc[ts].mean())
    games = games.join(exp.rename(columns={"ast_rate": "exp_ast", "blk_rate": "exp_blk"}))
    games["ast_effect"] = games.ast_rate - games.exp_ast
    games["blk_effect"] = games.blk_rate - games.exp_blk
    return games.groupby("arena")[["ast_effect", "blk_effect"]].mean()


def s2(pg, tg):
    rates = {s: arena_rates(tg[s]) for s in bt.SEASONS}
    pairs = {"ast": [], "blk": []}
    for a, b in zip(bt.SEASONS, bt.SEASONS[1:]):
        common = rates[a].index.intersection(rates[b].index)
        for stat in pairs:
            pairs[stat] += list(zip(rates[a].loc[common, f"{stat}_effect"], rates[b].loc[common, f"{stat}_effect"]))
    out = {}
    for stat, p in pairs.items():
        p = np.array(p)
        out[f"{stat}_yoy_corr"] = float(np.corrcoef(p.T)[0, 1])
        out[f"{stat}_effect_sd"] = float(p[:, 0].std())
    # Fantasy size: a 1 SD arena assist effect x ~40 made shots per game x 41 home games, split by two teams.
    league_fgm = float(tg[bt.SEASONS[-1]].FGM.mean())
    out["assists_per_home_game_for_1sd_arena_both_teams"] = out["ast_effect_sd"] * league_fgm * 2
    # Does last season's arena effect predict a team-changer's assist change? (players 20+ games both seasons)
    rows = []
    for a, b in zip(bt.SEASONS[1:], bt.SEASONS[2:]):
        pa = pg[a].groupby("PLAYER_ID").agg(ast=("AST", "mean"), n=("AST", "size"), team=("TEAM_ID", "last"))
        pb = pg[b].groupby("PLAYER_ID").agg(ast=("AST", "mean"), n=("AST", "size"), team=("TEAM_ID", "first"))
        ids = pa[(pa.n >= 20)].index.intersection(pb[pb.n >= 20].index)
        prior = rates[a]
        for pid in ids:
            ta, tb = pa.loc[pid, "team"], pb.loc[pid, "team"]
            if ta == tb or ta not in prior.index or tb not in prior.index:
                continue
            rows.append({"season": b, "PLAYER_ID": pid, "d_ast": pb.loc[pid, "ast"] - pa.loc[pid, "ast"],
                         "arena_change": (prior.loc[tb, "ast_effect"] - prior.loc[ta, "ast_effect"]) * pa.loc[pid, "ast"]})
    d = pd.DataFrame(rows)
    out["team_changers_n"] = len(d)
    out["team_changers_corr_arena_change_vs_assist_change"] = float(np.corrcoef(d.arena_change, d.d_ast)[0, 1]) if len(d) > 10 else None
    return out


def s3(pg, tg):
    frames = et.build(pg, tg)
    seasons = list(frames)
    rows = []
    for t in seasons:
        tr = pd.concat([frames[x] for x in seasons if x != t], ignore_index=True)
        te = frames[t].copy()
        for d in (tr, te):
            d["last"] = d.fp1
        curve = pp.fit_age_curve(tr.dropna(subset=["actual"]), "last")
        for d in (tr, te):
            d["bpv_fpg"] = pp.with_age(d, "last", curve) + CROWDING_COEF * d.crowding
            d["hybrid"] = 0.625 * d.bpv_fpg + 0.375 * d.espn_fpg
            d["disagree"] = (d.espn_fpg - d.bpv_fpg).abs()
        te = te.dropna(subset=["actual"])
        te["err"] = (te.actual - te.hybrid).abs()
        rows.append(te)
    d = pd.concat(rows, ignore_index=True)
    d["tercile"] = pd.qcut(d.disagree, 3, labels=["low", "mid", "high"])
    by = d.groupby("tercile").err.agg(["mean", "size"]).round(3).to_dict("index")
    # Current single band (between seasons): 80% of residuals within [-7.34, +6.21]? check coverage by tercile.
    resid = d.actual - d.hybrid
    lo, hi = resid.quantile(0.1), resid.quantile(0.9)
    cover = d.assign(inside=(resid >= lo) & (resid <= hi)).groupby("tercile").inside.mean().round(3).to_dict()
    # Leave-one-season-out tercile-specific bands: coverage per tercile.
    cov_new = []
    for t in seasons:
        tr, te = d[d.target != t], d[d.target == t]
        edges = tr.disagree.quantile([1 / 3, 2 / 3]).values
        def terc(x):
            return np.digitize(x, edges)
        trr = tr.actual - tr.hybrid
        bands = {k: (trr[terc(tr.disagree) == k].quantile(0.1), trr[terc(tr.disagree) == k].quantile(0.9)) for k in range(3)}
        ter = te.actual - te.hybrid
        k = terc(te.disagree)
        inside = [(bands[kk][0] <= r <= bands[kk][1]) for kk, r in zip(k, ter)]
        cov_new.append(pd.DataFrame({"k": k, "inside": inside}))
    cn = pd.concat(cov_new).groupby("k").inside.mean().round(3).to_dict()
    return {"n": len(d), "error_by_disagreement_tercile": by, "coverage_single_band_by_tercile": cover,
            "coverage_tercile_bands_leave_one_season_out": {["low", "mid", "high"][k]: v for k, v in cn.items()},
            "corr_disagreement_vs_error": float(np.corrcoef(d.disagree, d.err)[0, 1])}


def main():
    pg, tg = bt.load()
    res = {"S1": s1(pg)}
    res["S2"] = s2(pg, tg)
    print("S2", json.dumps(res["S2"], default=float), flush=True)
    res["S3"] = s3(pg, tg)
    print("S3", json.dumps(res["S3"], default=float), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
