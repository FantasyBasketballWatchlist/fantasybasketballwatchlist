"""Season totals: combine BPV and ESPN (per-game production x games played), preseason.

Run:  python -m analysis.test_espn_totals       (writes analysis/test_espn_totals.json)

ESPN beat BPV on season totals (test_espn_projections.py), most likely through its projected games
played, while a per-game blend beat both on FPTS/game. Here every combination of
  per game:  BPV (last season + age + roster crowding) | ESPN | blend (weight tuned leave-one-season-out)
  games:     BPV (availability x team games) | ESPN projected games | blend of the two (tuned)
is scored on actual season FPTS totals: absolute error, rank correlation, and 1,000 simulated drafts
per season, on everyone who qualified last season (0 if he then missed the season). Seasons 2021-22, 2023-24, 2024-25, 2025-26 (ESPN's 2022-23 projections aren't preseason).
"""
import json
import math
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp
from analysis import test_espn_projections as te_
from analysis import test_minutes_model as tmm
from analysis import test_misc as tm
from analysis import robustness as rb
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_espn_totals.json")
CROWDING_COEF = -0.0177
RNG = np.random.default_rng(17)


def build(pg, tg):
    """Everyone with 20+ games and 15+ mpg last season, scored on actual totals (0 if he missed the
    season); players who never played again (retirements) are dropped. `actual` (FPTS/game) is set
    only for players with 20+ games, and is used only to fit the per-game pieces."""
    names = te_.name_map(pg)
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    frames = {}
    for t, year in te_.ESPN_SEASONS.items():
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        hp = hist[(hist.season == prev) & (hist.played >= 20) & (hist.mpg >= 15)].set_index("PLAYER_ID")
        h_t = hist[hist.season == t].set_index("PLAYER_ID")
        later = set(hist[hist.season.map(bt.SEASONS.index) > bt.SEASONS.index(t)].PLAYER_ID)
        ids = [pid for pid in hp.index if pid in h_t.index or pid in later]
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID").AGE
        f = pd.DataFrame({"PLAYER_ID": ids, "target": t, "fp1": hp.loc[ids, "fpts_pg"].values,
                          "age": ages.reindex(ids).values})
        played = h_t.played.reindex(ids).fillna(0).values
        f["actual"] = np.where(played >= 20, h_t.fpts_pg.reindex(ids).values, np.nan)
        f["actual_total"] = h_t.fpts_total.reindex(ids).fillna(0).values
        ctx = tmm.roster_context(pg, t)
        f["crowding"] = f.PLAYER_ID.map(ctx.crowding).fillna(0)
        f, _ = te_.attach(f, te_.projections(year), names)
        p_league, _ = rb.league_before(hist, t)
        p_hat = bpv.predict_availability(hist, bt.SEASONS, prev, 0.5, 123, p_league)
        f["p_hat"] = f.PLAYER_ID.map(p_hat).fillna(p_league)
        f["team_games"] = int(tg[t].groupby("TEAM_ID").size().median())
        frames[t] = f.dropna(subset=["espn_fpg", "espn_gp", "age"])
    return frames


def main():
    pg, tg = bt.load()
    frames = build(pg, tg)
    seasons = list(frames)
    scored = []
    grid = np.round(np.arange(0, 1.001, 0.05), 2)
    for t in seasons:
        tr = pd.concat([frames[x] for x in seasons if x != t], ignore_index=True)
        te = frames[t].copy()
        for d in (tr, te):
            d["last"] = d.fp1
        curve = pp.fit_age_curve(tr.dropna(subset=["actual"]), "last")
        for d in (tr, te):
            d["bpv_fpg"] = pp.with_age(d, "last", curve) + CROWDING_COEF * d.crowding
            d["bpv_gp"] = d.p_hat * d.team_games
        trp = tr.dropna(subset=["actual"])
        w = min(grid, key=lambda w: bt.mae(w * trp.espn_fpg + (1 - w) * trp.bpv_fpg, trp.actual))
        for d in (tr, te):
            d["blend_fpg"] = w * d.espn_fpg + (1 - w) * d.bpv_fpg
        # Games weight tuned on actual totals with the blended per-game projection.
        wg = min(grid, key=lambda g: bt.mae(tr.blend_fpg * (g * tr.espn_gp + (1 - g) * tr.bpv_gp), tr.actual_total))
        te["w_fpg"], te["w_gp"] = w, wg
        for fpg in ("bpv_fpg", "espn_fpg", "blend_fpg"):
            te[f"{fpg}|bpv_gp"] = te[fpg] * te.bpv_gp
            te[f"{fpg}|espn_gp"] = te[fpg] * te.espn_gp
            te[f"{fpg}|blend_gp"] = te[fpg] * (wg * te.espn_gp + (1 - wg) * te.bpv_gp)
        scored.append(te)
    d = pd.concat(scored, ignore_index=True)
    combos = [c for c in d.columns if "|" in c]
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    res = {"n": len(d), "weights_fpg": d.groupby("target").w_fpg.first().to_dict(),
           "weights_games": d.groupby("target").w_gp.first().to_dict(),
           "mae_total": {c: bt.mae(d[c], d.actual_total) for c in combos},
           "spearman_mean": {c: float(np.mean([bt.spearman(g[c], g.actual_total) for _, g in d.groupby("target")])) for c in combos}}
    ref = "espn_fpg|espn_gp"          # ESPN on its own
    best = min(combos, key=lambda c: res["mae_total"][c])
    res["best_by_mae"] = best
    res["best_minus_espn_mae"] = tm.boot(d, np.abs(d[best] - d.actual_total), np.abs(d[ref] - d.actual_total), key="key")
    res["bpv_minus_espn_mae"] = tm.boot(d, np.abs(d["bpv_fpg|bpv_gp"] - d.actual_total), np.abs(d[ref] - d.actual_total), key="key")

    # Spearman difference with a within-season player bootstrap.
    def sp_diff(a, b, n=300):
        diffs = []
        for _ in range(n):
            vals = []
            for _, g in d.groupby("target"):
                idx = RNG.integers(0, len(g), len(g))
                s = g.iloc[idx]
                vals.append(bt.spearman(s[a], s.actual_total) - bt.spearman(s[b], s.actual_total))
            diffs.append(np.mean(vals))
        return {"diff": res["spearman_mean"][a] - res["spearman_mean"][b],
                "ci95": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]}
    best_sp = max(combos, key=lambda c: res["spearman_mean"][c])
    res["best_by_spearman"] = best_sp
    res["best_spearman_minus_espn"] = sp_diff(best_sp, ref) if best_sp != ref else None

    # Draft simulations: 5 strategies on each season's pool (players with an ESPN projection).
    strategies = [ref, "bpv_fpg|bpv_gp", "blend_fpg|bpv_gp", "blend_fpg|espn_gp", "blend_fpg|blend_gp"]
    sims = {}
    for t, g in d.groupby("target"):
        sim = g.set_index("PLAYER_ID")
        sims[t] = {k: v["mean"] for k, v in bt.simulate_drafts(sim, strategies, n_sims=1000).items()}
    res["draft_sim"] = sims
    res["draft_sim_mean"] = {s: float(np.mean([sims[t][s] for t in sims])) for s in strategies}
    res["draft_sim_wins"] = {s: sum(1 for t in sims if max(sims[t], key=sims[t].get) == s) for s in strategies}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
