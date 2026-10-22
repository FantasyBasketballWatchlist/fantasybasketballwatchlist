"""Availability for veterans ESPN doesn't project (rules: docs/prereg-no-espn-availability.md).

    python -m analysis.no_espn_availability        (writes analysis/no_espn_availability.json)
"""
import json
import os
import warnings

import numpy as np

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import bpv   # noqa: E402
import nba_data   # noqa: E402
from analysis import backtest as bt   # noqa: E402
from analysis import test_espn_projections as te_   # noqa: E402
from analysis import test_ten_team as ttt   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "no_espn_availability.json")
DESIGN, TEST = ["2021-22", "2023-24", "2024-25"], "2025-26"


def group(pg, tg, hist, lp, lq, names, t):
    df = ttt.season_frame(pg, tg, hist, lp, lq, t, names)
    prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
    mpg = hist[hist.season == prev].set_index("PLAYER_ID").mpg.reindex(df.index)
    games = int(tg[t].groupby("TEAM_ID").size().median())
    gp = pg[t][pg[t].MIN > 0].groupby("PLAYER_ID").size().reindex(df.index).fillna(0)
    g = df[(mpg >= 15) & ~np.isfinite(df[ttt.ESPN])]
    return g.p_hat.to_numpy(), (gp[g.index] / games).clip(upper=1).to_numpy()


def main():
    pg, tg = bt.load()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, nba_data.draft_history())
    lp, lq = bpv.league_availability(hist)
    names = te_.name_map(pg)
    data = {t: group(pg, tg, hist, lp, lq, names, t) for t in DESIGN + [TEST]}
    est = np.concatenate([data[t][0] for t in DESIGN]); act = np.concatenate([data[t][1] for t in DESIGN])
    s = float(act.sum() / est.sum())
    res = {"rules": "docs/prereg-no-espn-availability.md", "s": s, "seasons": {}}
    for t, (e, a) in data.items():
        res["seasons"][t] = {"players": len(e), "mae_current": float(np.abs(e - a).mean()), "mae_scaled": float(np.abs(e * s - a).mean()),
                             "bias_current": float((e - a).mean()), "bias_scaled": float((e * s - a).mean()), "role": "test" if t == TEST else "design"}
    r = res["seasons"][TEST]
    res["passes"] = bool(r["mae_scaled"] < r["mae_current"])
    with open(OUT, "w") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
