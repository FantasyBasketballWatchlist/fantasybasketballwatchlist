"""Exponential decay vs the last-5 rule for in-season production.

Run:  python -m analysis.decay_test
Same checkpoints, filters and tuning/test split as analysis/backtest.py (section A).
Models:
  season    season-to-date average
  8020      0.8 season + 0.2 last 5
  split     season + 0.3 minutes change + 0.1 per-minute change (current BPV)
  ewma(h)   every game weighted 0.5^(games ago / h)
  mxr(hm,hr) exponentially weighted minutes (half-life hm) x exponentially weighted FPTS per minute (half-life hr)
"""
import datetime as dt
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt

warnings.filterwarnings("ignore")
HALF_LIVES = [3, 5, 8, 12, 20, 30, 50, 1e9]
RNG = np.random.default_rng(5)


def ew(values, h):
    w = 0.5 ** (np.arange(len(values))[::-1] / h)
    return float((w * values).sum() / w.sum())


def rows_for(season, g_pg):
    cps = bt.checkpoints(g_pg, 28)
    out = []
    for pid, g in g_pg.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        dates, fp, mins = g.GAME_DATE.tolist(), g.FPTS.to_numpy(float), g.MIN.to_numpy(float)
        for c in cps:
            i = bisect_left(dates, c)
            if i < 10 or len(dates) - i < 10 or mins[:i].mean() < 12:
                continue
            f, m = fp[:i], mins[:i]
            row = {"season": season, "PLAYER_ID": pid, "S": f.mean(), "L5": f[-5:].mean(),
                   "mS": m.mean(), "mL5": m[-5:].mean(), "A": fp[i:].mean()}
            for h in HALF_LIVES:
                row[f"fp_{h}"] = ew(f, h)
                row[f"m_{h}"] = ew(m, h)
                w = 0.5 ** (np.arange(i)[::-1] / h)
                row[f"r_{h}"] = float((w * f).sum() / max((w * m).sum(), 1))
            out.append(row)
    return out


def mae(p, a):
    return float(np.mean(np.abs(p - a)))


def main():
    pg, _ = bt.load()
    df = pd.DataFrame([r for s in bt.TRAIN + bt.TEST for r in rows_for(s, pg[s])])
    tr, te = df[df.season.isin(bt.TRAIN)], df[df.season.isin(bt.TEST)]

    def split(d):
        per_min = d.S / d.mS.clip(lower=1)
        dm = per_min * (d.mL5 - d.mS)
        return d.S + 0.3 * dm + 0.1 * (d.L5 - d.S - dm)

    ewma = {h: mae(tr[f"fp_{h}"], tr.A) for h in HALF_LIVES}
    bh = min(ewma, key=ewma.get)
    mxr = {(hm, hr): mae(tr[f"m_{hm}"] * tr[f"r_{hr}"], tr.A) for hm in HALF_LIVES for hr in HALF_LIVES}
    bm, br = min(mxr, key=mxr.get)

    print(f"checkpoints: train {len(tr)}, test {len(te)}")
    print("EWMA of FPTS, train MAE by half-life (games):", {("season" if h == 1e9 else h): round(v, 3) for h, v in ewma.items()})
    print(f"best minutes x rate half-lives: minutes {bm}, per-minute {'season' if br == 1e9 else br} (train MAE {mxr[(bm, br)]:.3f})")
    models = {
        "season average": te.S, "80/20": 0.8 * te.S + 0.2 * te.L5, "split (current BPV)": split(te),
        f"EWMA half-life {bh}": te[f"fp_{bh}"], f"minutes(h={bm}) x rate(h={'season' if br == 1e9 else br})": te[f"m_{bm}"] * te[f"r_{br}"],
    }
    print("TEST 2025-26 MAE:")
    for name, p in models.items():
        print(f"  {name:32s} {mae(p, te.A):.3f}")
    best_name = min(models, key=lambda k: mae(models[k], te.A))
    ids = te.PLAYER_ID.unique()
    groups = te.reset_index(drop=True).groupby("PLAYER_ID").indices
    e = (np.abs(models[best_name] - te.A) - np.abs(models["split (current BPV)"] - te.A)).to_numpy()
    boots = [e[np.concatenate([groups[i] for i in RNG.choice(ids, len(ids))])].mean() for _ in range(400)]
    print(f"  best ({best_name}) minus current BPV: {e.mean():+.3f}  95% CI {np.percentile(boots, 2.5):+.3f} to {np.percentile(boots, 97.5):+.3f}")


if __name__ == "__main__":
    main()
