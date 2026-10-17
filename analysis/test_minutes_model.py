"""Offseason roster context: does knowing a player's team for the new season improve his preseason projection?

Run:  python -m analysis.test_minutes_model      (writes analysis/test_minutes_model.json)

Current preseason BPV production = last season's FPTS/game + age adjustment. Candidate features,
all known before a season starts (opening-night rosters are public):
  changed_team   he starts the new season on a different team
  crowding       total last-season minutes per game of his new teammates (players who open the
                 season on the same team and played 10+ mpg last season), minus the league average
  share          his own last-season minutes / (his minutes + crowding), a rough slice of the pie
A team's opening roster = players whose first game of the season came in its first 21 days.
Leave-one-season-out over 2022-23..2025-26, same player pool as preseason_production.py.
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(13)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_minutes_model.json")
FEATURES = {
    "changed_team": ["changed"],
    "crowding": ["crowding"],
    "crowding + changed_team": ["crowding", "changed"],
    "crowding x changed_team": ["crowding", "changed", "crowd_x_changed"],
}


def roster_context(pg, target):
    prev = bt.SEASONS[bt.SEASONS.index(target) - 1]
    g = pg[target].sort_values("GAME_DATE")
    start = dt.date.fromisoformat(g.GAME_DATE.min())
    first = g.groupby("PLAYER_ID").first()
    opening = first[first.GAME_DATE <= (start + dt.timedelta(days=21)).isoformat()]
    last_team = pg[prev].sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
    prev_mpg = pg[prev].groupby("PLAYER_ID").MIN.mean()
    team_of = opening.TEAM_ID
    contrib = prev_mpg.reindex(team_of.index).fillna(0)
    contrib = contrib.where(contrib >= 10, 0)
    team_total = contrib.groupby(team_of).sum()
    ctx = pd.DataFrame({"team": team_of})
    ctx["crowding_raw"] = ctx.team.map(team_total) - contrib
    ctx["crowding"] = ctx.crowding_raw - team_total.mean()
    ctx["changed"] = (last_team.reindex(ctx.index) != ctx.team).astype(float)
    return ctx


def main():
    pg, _ = bt.load()
    tab = pp.season_table(pg)
    frames = {}
    for t in pp.TARGETS:
        f = pp.frame(tab, t)
        ctx = roster_context(pg, t)
        f = f.merge(ctx[["crowding", "changed"]], left_on="PLAYER_ID", right_index=True, how="left")
        f["crowding"] = f.crowding.fillna(0)
        f["changed"] = f.changed.fillna(0)
        f["crowd_x_changed"] = f.crowding * f.changed
        frames[t] = f
    scored = []
    coefs = {k: [] for k in FEATURES}
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        tr["last"], te["last"] = tr.fp1, te.fp1
        curve = pp.fit_age_curve(tr, "last")
        tr["base"], te["base"] = pp.with_age(tr, "last", curve), pp.with_age(te, "last", curve)
        for name, cols in FEATURES.items():
            X = tr[cols].to_numpy()
            coef, *_ = np.linalg.lstsq(X, (tr.actual - tr.base).to_numpy(), rcond=None)
            te[name] = te.base + te[cols].to_numpy() @ coef
            if name == "crowding":
                te["crowding_pred"] = te[name]
            coefs[name].append([float(c) for c in coef])
        scored.append(te)
    d = pd.concat(scored, ignore_index=True)
    key = (d.PLAYER_ID.astype(str) + d.target).to_numpy()
    groups = pd.Series(range(len(d))).groupby(key).indices
    ids = list(groups)

    def boot(col, subset=None):
        e = (np.abs(d[col] - d.actual) - np.abs(d.base - d.actual)).to_numpy()
        idx = np.arange(len(d)) if subset is None else np.where(subset)[0]
        sub_groups = {k: np.intersect1d(v, idx) for k, v in groups.items()}
        sub_ids = [k for k in ids if len(sub_groups[k])]
        out = [e[np.concatenate([sub_groups[sub_ids[i]] for i in RNG.choice(len(sub_ids), len(sub_ids))])].mean() for _ in range(500)]
        return {"diff": float(e[idx].mean()), "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]}

    res = {"n": len(d), "share_changed_team": float(d.changed.mean()),
           "mae_current_last_plus_age": bt.mae(d.base, d.actual),
           "mean_residual_changed": float((d.actual - d.base)[d.changed == 1].mean()),
           "mean_residual_stayed": float((d.actual - d.base)[d.changed == 0].mean())}
    for name in FEATURES:
        b = boot(name)
        bc = boot(name, subset=(d.changed == 1).to_numpy())
        res[name] = {"mae": bt.mae(d[name], d.actual), "minus_current": b,
                     "verdict": "better" if b["ci95"][1] < 0 else "worse" if b["ci95"][0] > 0 else "tie",
                     "changed_team_players_only": bc, "coefs_by_fold": coefs[name]}
    # Final coefficient on all four seasons, and an 80% "likely range" for preseason production.
    allf = pd.concat(frames.values(), ignore_index=True)
    allf["last"] = allf.fp1
    curve_all = pp.fit_age_curve(allf, "last")
    allf["base"] = pp.with_age(allf, "last", curve_all)
    res["final_crowding_coef"] = float((allf.crowding * (allf.actual - allf.base)).sum() / (allf.crowding ** 2).sum())
    d["resid"] = d.actual - d.crowding_pred if "crowding_pred" in d else d.actual - d["crowding"]
    cover = []
    for t in pp.TARGETS:
        other = d[d.target != t].resid
        lo, hi = other.quantile(0.1), other.quantile(0.9)
        r = d[d.target == t].resid
        cover.append(float(((r >= lo) & (r <= hi)).mean()))
    res["preseason_band_80"] = [float(d.resid.quantile(0.1)), float(d.resid.quantile(0.9))]
    res["preseason_band_coverage_leave_one_season_out"] = cover
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
