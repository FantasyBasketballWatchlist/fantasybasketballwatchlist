"""ESPN's projected games -> availability: straight line vs a fitted curve (rules in docs/prereg-espn-games-curve.md).

    python -m analysis.espn_games_curve
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ["NBA_OFFLINE"] = "1"

import bpv   # noqa: E402
import nba_data   # noqa: E402
import ratings   # noqa: E402
from analysis import test_espn_projections as te   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "espn_games_curve.json")
STAR, BOOT = 40, 5000


def rows():
    out = []
    for s, y in te.ESPN_SEASONS.items():
        prev = bpv.add_fpts(nba_data.player_game_logs(nba_data.previous_season(s)))
        pv = prev.groupby("PLAYER_ID").agg(n=("MIN", "size"), mpg=("MIN", "mean"), fpg=("FPTS", "mean"),
                                           name=("PLAYER_NAME", "last"))
        pv = pv[(pv.n >= ratings.AGE_MIN_GAMES) & (pv.mpg >= ratings.AGE_MIN_MPG)]
        key_to_pid = {te.key(n): p for p, n in pv["name"].items()}
        now = bpv.add_fpts(nba_data.player_game_logs(s)).groupby("PLAYER_ID").agg(g=("FPTS", "size"), total=("FPTS", "sum"))
        seen = set()
        for pl in te.fetch(y)["players"]:
            p = pl["player"]
            pid = key_to_pid.get(te.key(p["fullName"]))
            if pid is None or pid in seen:
                continue
            proj = [st for st in p.get("stats", []) if st.get("statSourceId") == 1 and st.get("statSplitTypeId") == 0
                    and st.get("seasonId") == y]
            if proj:
                gp = float(proj[0]["stats"].get(te.GP_ID, 0.0))
                avg = proj[0].get("averageStats") or {}
                espn_fpg = te.fpts(avg) if avg else np.nan
                flagged = gp == 0
            elif p.get("injuryStatus") == "OUT":
                gp, espn_fpg, flagged = 0.0, np.nan, True
            else:
                continue
            seen.add(pid)
            prev_fpg = float(pv.loc[pid, "fpg"])
            # BPV's preseason production for the secondary metric: last season's FPTS/game blended with ESPN's.
            prod = prev_fpg if np.isnan(espn_fpg) else (1 - ratings.ESPN_FPG_WEIGHT) * prev_fpg + ratings.ESPN_FPG_WEIGHT * espn_fpg
            out.append({"season": s, "player": int(pid), "name": p["fullName"], "espn_gp": gp, "flagged": flagged,
                        "prev_fpg": prev_fpg, "production": prod,
                        "share": min(1.0, (now.loc[pid, "g"] if pid in now.index else 0) / ratings.SEASON_GAMES),
                        "total": float(now.loc[pid, "total"]) if pid in now.index else 0.0})
    return pd.DataFrame(out)


def isotonic(x, y):
    """Non-decreasing least-squares fit (pool adjacent violators), equal weights. Returns sorted (x, fitted)."""
    order = np.argsort(x, kind="stable")
    xs, ys = np.asarray(x, float)[order], np.asarray(y, float)[order]
    blocks = []                                   # [sum, count, x_min, x_max]
    for xi, yi in zip(xs, ys):
        blocks.append([yi, 1.0, xi, xi])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, c, lo, hi = blocks.pop()
            blocks[-1][0] += s; blocks[-1][1] += c; blocks[-1][3] = hi
    px, py = [], []
    for s, c, lo, hi in blocks:
        px += [lo, hi]
        py += [s / c, s / c]
    return np.array(px), np.array(py)


def c0(d):
    return np.where(d.flagged, ratings.ESPN_OUT_GAMES / ratings.SEASON_GAMES,
                    np.minimum(1.0, ratings.ESPN_GAMES_SCALE * d.espn_gp / ratings.SEASON_GAMES))


def compare(d, new, old):
    a = d.share.to_numpy()
    e1, e0 = (new - a) ** 2, (old - a) ** 2
    players = d.player.to_numpy()
    uniq = np.unique(players)
    idx = {p: np.flatnonzero(players == p) for p in uniq}
    rng = np.random.default_rng(7)
    diffs = [(lambda t: e1[t].mean() - e0[t].mean())(np.concatenate([idx[p] for p in rng.choice(uniq, len(uniq))]))
             for _ in range(BOOT)]
    by = {s: float(e1[m].mean() - e0[m].mean()) for s in d.season.unique() for m in [(d.season == s).to_numpy()]}
    star = (d.prev_fpg >= STAR).to_numpy()
    tot1 = np.abs(new * ratings.SEASON_GAMES * d.production - d.total)
    tot0 = np.abs(old * ratings.SEASON_GAMES * d.production - d.total)
    res = {"players": int(len(d)), "mse_c0": float(e0.mean()), "mse_c1": float(e1.mean()), "diff": float(e1.mean() - e0.mean()),
           "ci": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
           "by_season": {k: round(v, 5) for k, v in by.items()}, "seasons_better": f"{sum(v < 0 for v in by.values())} of {len(by)}",
           "stars": {"players": int(star.sum()), "diff": float(e1[star].mean() - e0[star].mean())},
           "mae_c0": float(np.abs(old - a).mean()), "mae_c1": float(np.abs(new - a).mean()),
           "season_total_err_c0": float(tot0.mean()), "season_total_err_c1": float(tot1.mean())}
    res["passes"] = bool(res["ci"][1] < 0 and sum(v < 0 for v in by.values()) >= 3 and res["stars"]["diff"] <= 0
                         and res["season_total_err_c1"] <= res["season_total_err_c0"])
    return res


LOW = 60


def main():
    d = rows()
    pred = np.empty(len(d))
    for s in d.season.unique():
        train, test = d[d.season != s], (d.season == s).to_numpy()
        px, py = isotonic(train.espn_gp, train.share)
        pred[test] = np.interp(d.espn_gp[test], px, py)
    old = c0(d)
    res = compare(d, pred, old)
    px, py = isotonic(d.espn_gp, d.share)
    curve = {int(g): round(float(np.interp(g, px, py)), 3) for g in [0, 10, 20, 30, 40, 50, 55, 60, 65, 70, 75, 82]}
    d["bucket"] = pd.cut(d.espn_gp, [-1, 0, 20, 40, 50, 60, 70, 90], labels=["0/out", "1-20", "21-40", "41-50", "51-60", "61-70", "71+"])
    table = d.assign(c0=old, c1=pred).groupby("bucket").agg(players=("share", "size"), actual=("share", "mean"),
                                                         c0=("c0", "mean"), c1=("c1", "mean")).round(3)
    # Addendum (post hoc): low-end-only correction, C2, against C0 with the recalibrated ESPN_OUT_GAMES.
    low = (d.espn_gp < LOW).to_numpy()
    pred2 = old.copy()
    for s in d.season.unique():
        train = d[(d.season != s) & (d.espn_gp < LOW)]
        m = (d.season == s).to_numpy() & low
        pred2[m] = train.share.mean()
    res2 = compare(d, pred2, old)
    res2["low_players"] = int(low.sum())
    out = {"rules": "docs/prereg-espn-games-curve.md", **res, "C2_low_end_vs_C0 (post hoc)": res2, "curve_all_seasons": curve,
           "by_projected_games": table.reset_index().astype({"bucket": str}).to_dict(orient="records")}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
