"""Preseason production: what best predicts next season's FPTS per game?

Run:  python -m analysis.preseason_production       (writes analysis/preseason_production.json)

Players with 20+ games in both the prior and target season and 15+ minutes per game in
the prior season. Every model is scored with leave-one-season-out: for each target season
(2022-23..2025-26), anything tuned (weights, shrinkage, age curve) is fitted on the other
three seasons only.

Models
  last            last season's FPTS/game (BPV before this test)
  last+age        last season + age-bucket adjustment
  fpg multi       games-weighted multi-season FPTS/game, shrunk to the league mean
  sps             Basketball-Reference's Simple Projection System applied to FPTS per minute:
                  6/3/1 minute-weighted seasons, regressed toward 1,000 league-average minutes,
                  its published age adjustment, times last season's minutes per game
  rate x min      tuned multi-season FPTS per minute x last season's minutes per game
  rate x min+age  the same plus a fitted age-bucket adjustment
"""
import itertools
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
import nba_data

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(3)
TARGETS = ["2022-23", "2023-24", "2024-25", "2025-26"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "preseason_production.json")
AGE_BUCKETS = ["<=21", "22-23", "24-26", "27-29", "30-32", "33+"]
WEIGHT_OPTIONS = [(1, 0, 0), (6, 3, 1), (5, 4, 3), (3, 2, 1), (2, 1, 0), (4, 2, 1), (1, 1, 1)]


def season_table(pg):
    rows = []
    for s, g in pg.items():
        t = g.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), gp=("FPTS", "size"), mpg=("MIN", "mean")).reset_index()
        ages = pd.read_csv(os.path.join(nba_data.CACHE_DIR, f"player_ages_{s}.csv"))[["PLAYER_ID", "AGE"]]
        t = t.merge(ages, on="PLAYER_ID", how="left")
        t["season"] = s
        rows.append(t)
    return pd.concat(rows, ignore_index=True)


def frame(tab, target):
    i = bt.SEASONS.index(target)
    prev = [bt.SEASONS[i - j] for j in (1, 2, 3)]
    by = {s: tab[tab.season == s].set_index("PLAYER_ID") for s in prev + [target]}
    base = by[prev[0]]
    base = base[(base.gp >= 20) & (base.mpg >= 15)]
    tgt = by[target]
    ids = base.index.intersection(tgt[tgt.gp >= 20].index)
    df = pd.DataFrame(index=ids)
    for j, s in enumerate(prev, 1):
        b = by[s]
        df[f"fp{j}"] = b.fp.reindex(ids)
        df[f"gp{j}"] = b.gp.reindex(ids).fillna(0)
        df[f"min{j}"] = (b.mpg * b.gp).reindex(ids).fillna(0)
        df[f"rate{j}"] = (b.fp / b.mpg.clip(lower=1)).reindex(ids)
    df["mpg1"] = base.mpg.reindex(ids)
    df["age"] = base.AGE.reindex(ids)
    df["actual"] = tgt.fp.reindex(ids)
    df["league_fpg"] = base.fp.mean()
    df["league_rate"] = (base.fp * base.gp).sum() / (base.mpg * base.gp).sum()   # total FPTS / total minutes
    df["target"] = target
    df["PLAYER_ID"] = ids
    return df.reset_index(drop=True)


def age_bucket(a):
    return "<=21" if a <= 21 else "22-23" if a <= 23 else "24-26" if a <= 26 else "27-29" if a <= 29 else "30-32" if a <= 32 else "33+"


def fpg_multi(df, w, k):
    num = sum(w[j] * df[f"gp{j + 1}"] * df[f"fp{j + 1}"].fillna(0) for j in range(3))
    den = sum(w[j] * df[f"gp{j + 1}"] for j in range(3))
    return (num + k * df.league_fpg) / (den + k)


def rate_multi(df, w, k_minutes):
    num = sum(w[j] * df[f"min{j + 1}"] * df[f"rate{j + 1}"].fillna(0) for j in range(3))
    den = sum(w[j] * df[f"min{j + 1}"] for j in range(3))
    return (num + k_minutes * df.league_rate) / (den + k_minutes)


def sps(df):
    rate = rate_multi(df, (6, 3, 1), 1000)
    age_next = df.age + 1
    factor = np.where(age_next < 28, 1 + (28 - age_next) * 0.004, 1 + (28 - age_next) * 0.002)
    return rate * factor * df.mpg1


def mae(p, a):
    return float(np.mean(np.abs(np.asarray(p) - np.asarray(a))))


def fit_age_curve(train, pred_col):
    return (train.actual - train[pred_col]).groupby(train.age.map(age_bucket)).mean()


def with_age(df, pred_col, curve):
    return df[pred_col] + df.age.map(age_bucket).map(curve).fillna(0)


def boot_diff(df, p1, p2, n=500):
    keys = (df.PLAYER_ID.astype(str) + df.target).to_numpy()
    groups = pd.Series(range(len(df))).groupby(keys).indices
    ids = list(groups)
    e = np.abs(p1 - df.actual).to_numpy() - np.abs(p2 - df.actual).to_numpy()
    out = [e[np.concatenate([groups[ids[i]] for i in RNG.choice(len(ids), len(ids))])].mean() for _ in range(n)]
    return float(e.mean()), [float(x) for x in np.percentile(out, [2.5, 97.5])]


def main():
    pg, _ = bt.load()
    tab = season_table(pg)
    frames = {t: frame(tab, t) for t in TARGETS}
    scored, tuned = [], {}
    for t in TARGETS:
        tr = pd.concat([frames[x] for x in TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        # Tune on the other seasons.
        g1 = {(w, k): mae(fpg_multi(tr, w, k), tr.actual) for w, k in itertools.product(WEIGHT_OPTIONS, [0, 10, 25, 50])}
        w1, k1 = min(g1, key=g1.get)
        g2 = {(w, k): mae(rate_multi(tr, w, k) * tr.mpg1, tr.actual)
              for w, k in itertools.product(WEIGHT_OPTIONS, [0, 250, 500, 1000, 2000])}
        w2, k2 = min(g2, key=g2.get)
        tr["last"] = tr.fp1
        tr["rxm"] = rate_multi(tr, w2, k2) * tr.mpg1
        curve_last, curve_rxm = fit_age_curve(tr, "last"), fit_age_curve(tr, "rxm")
        tuned[t] = {"fpg_weights": w1, "fpg_k": k1, "rate_weights": w2, "rate_k_minutes": k2,
                    "age_curve_last": curve_last.to_dict(), "age_curve_rate_x_min": curve_rxm.to_dict()}
        # Score on the held-out season.
        te["last"] = te.fp1
        te["last+age"] = with_age(te, "last", curve_last)
        te["fpg multi"] = fpg_multi(te, w1, k1)
        te["sps"] = sps(te)
        te["rate x min"] = rate_multi(te, w2, k2) * te.mpg1
        te["rate x min+age"] = with_age(te, "rate x min", curve_rxm)
        scored.append(te)
    df = pd.concat(scored, ignore_index=True)
    models = ["last", "last+age", "fpg multi", "sps", "rate x min", "rate x min+age"]
    res = {"n": len(df), "tuned": tuned,
           "mae": {m: mae(df[m], df.actual) for m in models},
           "mae_by_season": {t: {m: mae(g[m], g.actual) for m in models} for t, g in df.groupby("target")},
           "spearman": {m: bt.spearman(df[m], df.actual) for m in models}}
    best = min(models, key=lambda m: res["mae"][m])
    res["best"] = best
    for m in models:
        if m != "last":
            d, c = boot_diff(df, df[m], df["last"])
            res[f"{m} minus last"] = {"diff": d, "ci95": c}
    for other in ["last+age", "sps"]:
        if other != best:
            d, c = boot_diff(df, df[best], df[other])
            res[f"{best} minus {other}"] = {"diff": d, "ci95": c}
    # Final age curve for the app: fitted on all four seasons for the best model's form.
    df_all = pd.concat(frames.values(), ignore_index=True)
    if best.startswith("rate x min"):
        tr_all = df_all.copy()
        g = {(w, k): mae(rate_multi(tr_all, w, k) * tr_all.mpg1, tr_all.actual)
             for w, k in itertools.product(WEIGHT_OPTIONS, [0, 250, 500, 1000, 2000])}
        w, k = min(g, key=g.get)
        tr_all["pred"] = rate_multi(tr_all, w, k) * tr_all.mpg1
        res["final"] = {"form": "rate x min", "rate_weights": w, "rate_k_minutes": k}
    else:
        tr_all = df_all.copy()
        tr_all["pred"] = tr_all.fp1
        res["final"] = {"form": "last"}
    curve = fit_age_curve(tr_all, "pred")
    res["final"]["age_curve"] = {b: float(curve.get(b, 0.0)) for b in AGE_BUCKETS}
    res["final"]["age_curve_n"] = {b: int((tr_all.age.map(age_bucket) == b).sum()) for b in AGE_BUCKETS}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=lambda o: list(o) if isinstance(o, tuple) else float(o))
    print(json.dumps({k: v for k, v in res.items() if k != "tuned"}, indent=1, default=str))


if __name__ == "__main__":
    main()
