"""Frozen BPV + ESPN blend on ESPN's two older genuine preseason seasons (2018-19, 2020-21).

Run:  python -m analysis.holdout_espn        (writes analysis/holdout_espn.json)

Rules and criteria (E1-E4) were written first: docs/holdout-preregistration.md, addendum.
"""
import json
import os
import warnings

import numpy as np

from analysis import backtest as bt
from analysis import test_espn_projections as te_
from analysis import test_espn_totals as tet
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "holdout_espn.json")
bt.SEASONS = [nba_data.season_string(y) for y in range(2009, 2021)]
te_.ESPN_SEASONS = {"2018-19": 2019, "2020-21": 2021}
W = ratings.ESPN_FPG_WEIGHT
SCALE = ratings.ESPN_GAMES_SCALE


def main():
    pg, tg = bt.load()
    frames = tet.build(pg, tg)
    res = {}
    for t, f in frames.items():
        f = f.copy()
        f["bpv_fpg"] = f.fp1 + f.age.map(lambda a: ratings.AGE_CURVE[bpv.age_bucket(a)]) + ratings.CROWDING_COEF * f.crowding
        f["hyb_fpg"] = (1 - W) * f.bpv_fpg + W * f.espn_fpg
        f["BPV"] = f.bpv_fpg * f.p_hat * f.team_games
        f["ESPN"] = f.espn_fpg * f.espn_gp
        f["Hybrid"] = f.hyb_fpg * np.minimum(f.team_games, SCALE * f.espn_gp)
        f["ESPN per game, BPV games"] = f.espn_fpg * f.p_hat * f.team_games
        f["BPV per game, ESPN games"] = f.bpv_fpg * f.espn_gp
        pgm = f.dropna(subset=["actual"])
        per_game = {"BPV": bt.mae(pgm.bpv_fpg, pgm.actual), "ESPN": bt.mae(pgm.espn_fpg, pgm.actual),
                    "Hybrid": bt.mae(pgm.hyb_fpg, pgm.actual), "players": len(pgm)}
        models = ["BPV", "ESPN", "Hybrid"]
        rank = {m: bt.spearman(f[m], f.actual_total) for m in models}
        total = {m: bt.mae(f[m], f.actual_total) for m in models}
        field = models + ["ESPN per game, BPV games", "BPV per game, ESPN games"]
        sims = {k: v["mean"] for k, v in bt.simulate_drafts(f.set_index("PLAYER_ID"), field, n_sims=1000).items()}
        res[t] = {"players": len(f), "per_game_error": per_game, "rank_corr": rank, "total_error": total, "drafts": sims,
                  "E1": per_game["Hybrid"] < min(per_game["BPV"], per_game["ESPN"]),
                  "E2": rank["Hybrid"] > max(rank["BPV"], rank["ESPN"]),
                  "E3": total["Hybrid"] < total["ESPN"],
                  "E4": sims["Hybrid"] > sims["ESPN"]}
        print(t, json.dumps(res[t], default=float), flush=True)
    seasons = list(res)
    res["confirmed"] = all(res[t]["E1"] and res[t]["E2"] for t in seasons)
    res["contradicted"] = all(res[t]["rank_corr"]["Hybrid"] < max(res[t]["rank_corr"]["BPV"], res[t]["rank_corr"]["ESPN"]) for t in seasons)
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=float)
    print("confirmed", res["confirmed"], "contradicted", res["contradicted"])


if __name__ == "__main__":
    main()
