"""Four more candidate improvements, each scored against current BPV out of sample.

Run:  python -m analysis.test_misc        (writes analysis/test_misc.json)

T1  Early-season blend: use last season + age adjustment as the prior (instead of last season).
T2  Averaging: 50/50 (and tuned) blend of BPV's preseason production with Basketball-Reference's SPS.
T3  Recent-form window: last 3, 7, 10 or 15 games instead of 5 (weights refit for each).
T4  Long-term teammate absences: when a 20+ minute teammate is out for the rest of the season
    (missed the team's last 3 games and plays in at most 10% of the rest), does the player's
    rest-of-season FPTS/game beat BPV's projection? Fitted on 2021-22..2024-25, scored on 2025-26.
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
import bpv
import nba_data

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(21)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_misc.json")


def boot(df, err_new, err_old, key="PLAYER_ID", n=500):
    e = (np.asarray(err_new) - np.asarray(err_old))
    groups = pd.Series(range(len(df))).groupby(df[key].astype(str).to_numpy()).indices
    ids = list(groups)
    out = [e[np.concatenate([groups[ids[i]] for i in RNG.choice(len(ids), len(ids))])].mean() for _ in range(n)]
    return {"diff": float(e.mean()), "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]}


def verdict(b):
    lo, hi = b["ci95"]
    return "better" if hi < 0 else "worse" if lo > 0 else "tie"


# ---------------------------------------------------------------- T1
def t1_early_season_age(pg, tg):
    rows = []
    for s in bt.SEASONS[3:]:
        curve = bt.age_curve_before(pg, s)
        prev = bt.SEASONS[bt.SEASONS.index(s) - 1]
        g = pg[prev].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), gp=("FPTS", "size"), mpg=("MIN", "mean"))
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID")["AGE"]
        cp = bt.checkpoint_rows(s, pg[s], tg[s], first_offset_days=7, min_before=1, min_after=10)
        cp = cp[cp.n_before <= 20]
        for r in cp.itertuples():
            if r.PLAYER_ID not in g.index or g.loc[r.PLAYER_ID].gp < 20:
                continue
            prior = g.loc[r.PLAYER_ID].fp
            adj = curve.get(bpv.age_bucket(ages[r.PLAYER_ID]), 0.0) if (r.PLAYER_ID in ages.index and g.loc[r.PLAYER_ID].mpg >= 15) else 0.0
            rows.append({"PLAYER_ID": f"{r.PLAYER_ID}-{s}", "A": r.A_ros,
                         "cur": bpv.shrink(r.S, r.n_before, prior, 8), "new": bpv.shrink(r.S, r.n_before, prior + adj, 8)})
    d = pd.DataFrame(rows)
    b = boot(d, np.abs(d.new - d.A), np.abs(d.cur - d.A))
    return {"n": len(d), "mae_current": bt.mae(d.cur, d.A), "mae_new": bt.mae(d.new, d.A), "new_minus_current": b, "verdict": verdict(b)}


# ---------------------------------------------------------------- T2
def t2_averaging(pg):
    tab = pp.season_table(pg)
    frames = {t: pp.frame(tab, t) for t in pp.TARGETS}
    out = []
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        tr["last"], te["last"] = tr.fp1, te.fp1
        curve = pp.fit_age_curve(tr, "last")
        for d in (tr, te):
            d["bpv"] = pp.with_age(d, "last", curve)
            d["sps"] = pp.sps(d)
        weights = np.round(np.arange(0, 1.01, 0.1), 1)
        w = min(weights, key=lambda w: bt.mae((1 - w) * tr.bpv + w * tr.sps, tr.actual))
        te["avg50"] = 0.5 * te.bpv + 0.5 * te.sps
        te["avg_tuned"] = (1 - w) * te.bpv + w * te.sps
        te["w"] = w
        out.append(te)
    d = pd.concat(out, ignore_index=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    res = {"n": len(d), "mae_bpv": bt.mae(d.bpv, d.actual), "mae_sps": bt.mae(d.sps, d.actual),
           "mae_avg50": bt.mae(d.avg50, d.actual), "mae_avg_tuned": bt.mae(d.avg_tuned, d.actual),
           "tuned_sps_weights": sorted(set(float(x) for x in d.w))}
    for m in ("avg50", "avg_tuned"):
        b = boot(d, np.abs(d[m] - d.actual), np.abs(d.bpv - d.actual), key="key")
        res[f"{m}_minus_bpv"] = b
        res[f"{m}_verdict"] = verdict(b)
    return res


# ---------------------------------------------------------------- T3
WINDOWS = [3, 5, 7, 10, 15]


def window_rows(season, g_pg):
    cps = bt.checkpoints(g_pg, 28)
    out = []
    for pid, g in g_pg.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        dates, fp, mins = g.GAME_DATE.tolist(), g.FPTS.to_numpy(float), g.MIN.to_numpy(float)
        for c in cps:
            i = bisect_left(dates, c)
            if i < 15 or len(dates) - i < 10 or mins[:i].mean() < 12:
                continue
            row = {"season": season, "PLAYER_ID": pid, "S": fp[:i].mean(), "mS": mins[:i].mean(), "A": fp[i:].mean()}
            for w in WINDOWS:
                row[f"L{w}"], row[f"m{w}"] = fp[i - w:i].mean(), mins[i - w:i].mean()
            out.append(row)
    return out


def t3_window(pg):
    d = pd.DataFrame([r for s in bt.TRAIN + bt.TEST for r in window_rows(s, pg[s])])
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)

    def parts(x, w):
        per_min = x.S / x.mS.clip(lower=1)
        dm = per_min * (x[f"m{w}"] - x.mS)
        return dm, x[f"L{w}"] - x.S - dm

    res, errs = {"n_train": len(tr), "n_test": len(te)}, {}
    for w in WINDOWS:
        dm, de = parts(tr, w)
        coef, *_ = np.linalg.lstsq(np.column_stack([dm, de]), (tr.A - tr.S).to_numpy(), rcond=None)
        tdm, tde = parts(te, w)
        pred = te.S + coef[0] * tdm + coef[1] * tde
        errs[w] = np.abs(pred - te.A).to_numpy()
        res[f"L{w}"] = {"weights": [float(c) for c in coef], "test_mae": float(errs[w].mean())}
    for w in WINDOWS:
        if w != 5:
            b = boot(te, errs[w], errs[5])
            res[f"L{w}_minus_L5"] = b
            res[f"L{w}_verdict"] = verdict(b)
    return res


# ---------------------------------------------------------------- T4
def t4_teammates_out(pg, tg):
    rows = []
    for s in bt.TRAIN + bt.TEST:
        g_all = pg[s].sort_values("GAME_DATE")
        sched = {t: sorted(x) for t, x in tg[s].groupby("TEAM_ID").GAME_DATE}
        by_player = {pid: g for pid, g in g_all.groupby("PLAYER_ID")}
        for c in bt.checkpoints(g_all, 28):
            before = g_all[g_all.GAME_DATE < c]
            after = g_all[g_all.GAME_DATE >= c]
            stats = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"),
                                                    team=("TEAM_ID", "last"), last=("GAME_DATE", "max"))
            after_n = after.groupby("PLAYER_ID").size()
            # Teammates known to be out long-term: 20+ mpg, missed the team's last 3 games, play <=10% of the rest.
            lost = {}
            for pid, st in stats[(stats.mpg >= 20) & (stats.n >= 10)].iterrows():
                sch = sched[st.team]
                j = bisect_left(sch, c)
                remaining = len(sch) - j
                if remaining < 10 or j < 3 or st["last"] >= sch[j - 3]:
                    continue
                if after_n.get(pid, 0) <= 0.1 * remaining:
                    lost[st.team] = lost.get(st.team, 0.0) + st.mpg
            for pid, st in stats[(stats.n >= 10) & (stats.mpg >= 12)].iterrows():
                if after_n.get(pid, 0) < 10:
                    continue
                g = by_player[pid]
                prior = g[g.GAME_DATE < c]
                l5 = prior.tail(5)
                per_min = st.fp / max(st.mpg, 1)
                dm = per_min * (l5.MIN.mean() - st.mpg)
                pred = st.fp + 0.3 * dm + 0.1 * (l5.FPTS.mean() - st.fp - dm)
                rows.append({"season": s, "PLAYER_ID": pid, "pred": pred, "fpm": per_min,
                             "A": g[g.GAME_DATE >= c].FPTS.mean(), "lost": lost.get(st.team, 0.0)})
    d = pd.DataFrame(rows)
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)
    res = {"n_train": len(tr), "n_test": len(te), "share_rows_with_lost_teammate": float((d.lost > 0).mean())}
    for label, x_tr, x_te in [("b x lost minutes", tr.lost, te.lost),
                              ("b x lost minutes x FPTS per minute", tr.lost * tr.fpm, te.lost * te.fpm)]:
        b = float((x_tr * (tr.A - tr.pred)).sum() / (x_tr ** 2).sum())
        new = te.pred + b * x_te
        bb = boot(te, np.abs(new - te.A), np.abs(te.pred - te.A))
        sub = te[te.lost > 0]
        bsub = boot(sub.reset_index(drop=True), np.abs(sub.pred + b * (x_te[te.lost > 0]) - sub.A), np.abs(sub.pred - sub.A))
        res[label] = {"coef": b, "all_rows": bb, "rows_with_lost_teammate": bsub, "verdict_all": verdict(bb),
                      "verdict_affected": verdict(bsub), "n_affected_test": len(sub)}
    res["train_mean_residual_when_lost"] = float((tr.A - tr.pred)[tr.lost > 0].mean())
    res["train_mean_residual_otherwise"] = float((tr.A - tr.pred)[tr.lost == 0].mean())
    return res


def main():
    pg, tg = bt.load()
    res = {"T1_early_season_age": t1_early_season_age(pg, tg)}
    print("T1", json.dumps(res["T1_early_season_age"]), flush=True)
    res["T2_averaging_with_sps"] = t2_averaging(pg)
    print("T2", json.dumps(res["T2_averaging_with_sps"]), flush=True)
    res["T3_window_length"] = t3_window(pg)
    print("T3", json.dumps(res["T3_window_length"]), flush=True)
    res["T4_teammates_out"] = t4_teammates_out(pg, tg)
    print("T4", json.dumps(res["T4_teammates_out"]), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)


if __name__ == "__main__":
    main()
