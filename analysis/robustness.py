"""Stress tests for the backtest conclusions.

Run:  python -m analysis.robustness      (writes analysis/robustness.json)

R1  Recency weight: bootstrap (resampling players) the best weight; per-season best
    weights; confidence intervals on test-season error differences.
R2  New Role Value: how flat the error surface is around the best haircut/weight.
R3  Minutes vs efficiency split: bootstrap the two weights and the test improvement.
R4  Preseason model comparison with no leakage: availability settings and league
    averages tuned only on seasons before each target; fair target (actual FPTS).
R5  Are absence patterns (long vs scattered) a stable trait? Several measures,
    within-season split-half reliability, and a disattenuated year-to-year correlation.
R6  Availability: confidence interval for "shrunk history beats league average".
"""
import json
import os
import warnings
from bisect import bisect_left, bisect_right

import numpy as np
import pandas as pd

from analysis import backtest as bt
import bpv

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(11)
B = 300
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robustness.json")


def ci(values):
    lo, hi = np.percentile(values, [2.5, 97.5])
    return [float(lo), float(hi)]


def player_bootstrap(df, stat, n=B):
    """Resample players (all their rows together) and recompute stat(df)."""
    groups = {pid: idx for pid, idx in df.groupby("PLAYER_ID").indices.items()}
    ids = list(groups)
    out = []
    for _ in range(n):
        pick = RNG.choice(len(ids), len(ids))
        rows = np.concatenate([groups[ids[i]] for i in pick])
        out.append(stat(df.iloc[rows]))
    return out


# ---------------------------------------------------------------- R1 / R3
def r1_r3(cp):
    res = {}
    weights = np.round(np.arange(0, 0.51, 0.05), 2)
    tr = cp[cp.season.isin(bt.TRAIN)].dropna(subset=["A_ros"]).reset_index(drop=True)
    te = cp[cp.season.isin(bt.TEST)].dropna(subset=["A_ros"]).reset_index(drop=True)

    def best_w(df):
        errs = [np.mean(np.abs((1 - w) * df.S + w * df.L5 - df.A_ros)) for w in weights]
        return float(weights[int(np.argmin(errs))])

    boot = player_bootstrap(tr, best_w)
    res["R1_best_weight_bootstrap"] = {"distribution": {str(w): boot.count(w) / len(boot) for w in sorted(set(boot))},
                                       "ci95": ci(boot)}
    res["R1_best_weight_by_season"] = {s: best_w(g.dropna(subset=["A_ros"])) for s, g in cp.groupby("season")}
    grid_by_season = {s: {str(w): float(np.mean(np.abs((1 - w) * g.S + w * g.L5 - g.A_ros))) for w in weights}
                      for s, g in cp.dropna(subset=["A_ros"]).groupby("season")}
    res["R1_mae_by_season"] = grid_by_season

    def diff(df, w1, w2):
        e1 = np.abs((1 - w1) * df.S + w1 * df.L5 - df.A_ros)
        e2 = np.abs((1 - w2) * df.S + w2 * df.L5 - df.A_ros)
        return float(np.mean(e1 - e2))
    res["R1_test_diff_20_minus_15"] = {"point": diff(te, .2, .15), "ci95": ci(player_bootstrap(te, lambda d: diff(d, .2, .15)))}
    res["R1_test_diff_20_minus_0"] = {"point": diff(te, .2, 0), "ci95": ci(player_bootstrap(te, lambda d: diff(d, .2, 0)))}
    res["R1_test_mae_0"] = float(np.mean(np.abs(te.S - te.A_ros)))

    # R3: minutes vs efficiency split.
    def fit(df):
        d_min = df.fpm_S * (df.mpg_L5 - df.mpg_S)
        d_rate = df.L5 - df.S - d_min
        coef, *_ = np.linalg.lstsq(np.column_stack([d_min, d_rate]), (df.A_ros - df.S).to_numpy(), rcond=None)
        return coef
    coef = fit(tr)
    coefs = np.array(player_bootstrap(tr, fit))
    res["R3_weights"] = {"minutes": float(coef[0]), "minutes_ci95": ci(coefs[:, 0]),
                         "efficiency": float(coef[1]), "efficiency_ci95": ci(coefs[:, 1]),
                         "minutes_minus_efficiency_ci95": ci(coefs[:, 0] - coefs[:, 1])}

    def split_vs_8020(df):
        d_min = df.fpm_S * (df.mpg_L5 - df.mpg_S)
        split = df.S + coef[0] * d_min + coef[1] * (df.L5 - df.S - d_min)
        return float(np.mean(np.abs(split - df.A_ros) - np.abs(0.8 * df.S + 0.2 * df.L5 - df.A_ros)))
    res["R3_test_split_minus_8020"] = {"point": split_vs_8020(te), "ci95": ci(player_bootstrap(te, split_vs_8020))}
    return res


# ---------------------------------------------------------------- R2
def r2(cp):
    role = cp[(cp.mpg_L5 - cp.mpg_S >= 8) & (cp.mpg_S <= 24)].dropna(subset=["A_ros"]).copy().reset_index(drop=True)
    role["M2"] = 0.8 * role.S + 0.2 * role.L5
    tr, te = role[role.season.isin(bt.TRAIN)], role[role.season.isin(bt.TEST)]
    hs, bs = np.round(np.arange(0.6, 1.11, 0.05), 2), np.round(np.arange(0, 1.01, 0.1), 1)

    def mae_hb(df, h, b):
        return float(np.mean(np.abs((1 - b) * df.M2 + b * df.fpm_S * df.mpg_L5 * h - df.A_ros)))
    grid = {(h, b): mae_hb(tr, h, b) for h in hs for b in bs}
    best = min(grid.values())
    near = sorted([(h, b, v) for (h, b), v in grid.items() if v <= best * 1.01], key=lambda x: x[2])

    def best_pair(df):
        g = {(h, b): mae_hb(df, h, b) for h in hs for b in bs}
        return min(g, key=g.get)
    boot = player_bootstrap(tr, best_pair, n=150)
    haircuts = [h for h, _ in boot]
    # How much does New Role Value beat 80/20 on the unseen season, with uncertainty?
    gain = lambda d: mae_hb(d, 0.9, 0.5) - float(np.mean(np.abs(d.M2 - d.A_ros)))
    return {"n_train": len(tr), "n_test": len(te), "n_players_train": int(tr.PLAYER_ID.nunique()),
            "pairs_within_1pct_of_best": [[float(h), float(b), round(v, 3)] for h, b, v in near],
            "bootstrap_best_haircut_ci95": ci(haircuts),
            "bootstrap_best_haircut_share_0.90": haircuts.count(0.9) / len(haircuts),
            "test_nrv_minus_8020": {"point": gain(te), "ci95": ci(player_bootstrap(te, gain))}}


# ---------------------------------------------------------------- R4 / R6
def league_before(hist, season):
    return bpv.league_availability(hist[hist.season.map(bt.SEASONS.index) < bt.SEASONS.index(season)])


def availability_errors(hist, target, decay, k):
    prev = bt.SEASONS[bt.SEASONS.index(target) - 1]
    ids = set(hist[(hist.season == prev) & (hist.mpg >= 20) & (hist.played >= 20)].PLAYER_ID)
    actual = hist[(hist.season == target) & hist.PLAYER_ID.isin(ids)].set_index("PLAYER_ID").availability
    p_league, _ = league_before(hist, target)
    pred = bt.predict_availability(hist, target, decay, k, p_league).reindex(actual.index)
    return pd.DataFrame({"PLAYER_ID": actual.index, "err": np.abs(pred.values - actual.values),
                         "err_league": np.abs(p_league - actual.values),
                         "err_career": np.abs(bt.predict_availability(hist, target, 1.0, 0, p_league)
                                              .reindex(actual.index).values - actual.values)})


def tune_availability(hist, targets):
    options = [(d, k) for d in (1.0, 0.85, 0.7, 0.5, 0.0001) for k in (0, 20, 41, 82, 123, 164, 246)]
    score = {o: np.mean([availability_errors(hist, t, *o).err.mean() for t in targets]) for o in options}
    return min(score, key=score.get)


def r4_r6(pg, hist):
    res = {"R4": {}, "R6": {}}
    rows6 = []
    for target in bt.SEASONS[3:]:
        tuning_targets = bt.SEASONS[2:bt.SEASONS.index(target)]
        decay, k = tune_availability(hist, tuning_targets)
        p_league, q_league = league_before(hist, target)
        # Predictions use only seasons before `target`; later seasons are read only to drop retirements.
        df_full, _ = bt.preseason_frame(pg, hist, target, decay, k, p_league, q_league,
                                        age_curve=bt.age_curve_before(pg, target))
        pool = df_full[df_full.S >= 15].copy()
        pool["PLAYER_ID"] = pool.index
        sp = {m: bt.spearman(pool[m], pool.actual_total) for m in bt.MODELS}

        def d(a, b):
            return lambda x: bt.spearman(x[a], x.actual_total) - bt.spearman(x[b], x.actual_total)
        strategies = ["M3 x career GP%", "M5 80/20 x career GP%", "BPV (replacement-level)", "BPV + age",
                      "Last season total FPTS"]
        sims = bt.simulate_drafts(df_full.dropna(subset=strategies), strategies, n_sims=1000)
        res["R4"][target] = {
            "tuned_on": tuning_targets, "decay": decay, "k": k, "league_p": p_league, "league_q": q_league,
            "spearman_total": sp,
            "bpv_minus_m5_ci95": ci(player_bootstrap(pool.reset_index(drop=True), d("BPV (replacement-level)", "M5 80/20 x career GP%"), n=200)),
            "bpv_minus_m1_ci95": ci(player_bootstrap(pool.reset_index(drop=True), d("BPV (replacement-level)", "M1 season FPTS"), n=200)),
            "bpv_age_minus_m5_ci95": ci(player_bootstrap(pool.reset_index(drop=True), d("BPV + age", "M5 80/20 x career GP%"), n=200)),
            "bpv_age_minus_bpv_ci95": ci(player_bootstrap(pool.reset_index(drop=True), d("BPV + age", "BPV (replacement-level)"), n=200)),
            "draft_sim_total": {s: v["mean"] for s, v in sims.items()},
        }
        e = availability_errors(hist, target, decay, k)
        e["target"] = target
        rows6.append(e)
    e = pd.concat(rows6, ignore_index=True)
    res["R6"] = {
        "mae_shrunk_out_of_sample": float(e.err.mean()), "mae_league_average": float(e.err_league.mean()),
        "mae_career_gp": float(e.err_career.mean()),
        "shrunk_minus_league_ci95": ci(player_bootstrap(e, lambda x: x.err.mean() - x.err_league.mean())),
        "career_minus_league_ci95": ci(player_bootstrap(e, lambda x: x.err_career.mean() - x.err_league.mean())),
        "n": len(e),
    }
    return res


# ---------------------------------------------------------------- R5
def tagged_gaps(season_pg, season_tg):
    """player -> list of (gap_length, position, midpoint_date) with position in start/middle/end."""
    sched = {t: sorted(d) for t, d in season_tg.groupby("TEAM_ID").GAME_DATE}
    out = {}
    for pid, g in season_pg.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        app = list(zip(g.GAME_DATE, g.TEAM_ID))
        gaps = []
        d0, t0 = app[0]
        n = bisect_left(sched[t0], d0)
        if n:
            gaps.append((n, "start", d0))
        for (d1, t1), (d2, t2) in zip(app, app[1:]):
            c = lambda t: max(0, bisect_left(sched[t], d2) - bisect_right(sched[t], d1))
            n = c(t1) if t1 == t2 else min(c(t1), c(t2))
            if n:
                gaps.append((n, "middle", d1))
        dl, tl = app[-1]
        n = len(sched[tl]) - bisect_right(sched[tl], dl)
        if n:
            gaps.append((n, "end", dl))
        out[pid] = {"gaps": gaps, "mpg": g.MIN.mean(), "mid_date": g.GAME_DATE.iloc[len(g) // 2]}
    return out


def q_of(gaps, threshold, positions=("start", "middle", "end")):
    use = [n for n, pos, _ in gaps if pos in positions]
    missed = sum(use)
    return (sum(n for n in use if n >= threshold) / missed, missed) if missed else (np.nan, 0)


def r5(pg, tg):
    tagged = {s: tagged_gaps(pg[s], tg[s]) for s in bt.SEASONS}
    season_mid = {s: sorted(pg[s].GAME_DATE.unique())[len(pg[s].GAME_DATE.unique()) // 2] for s in bt.SEASONS}
    variants = {
        "baseline (all gaps, 5+ = long, 20+ mpg)": dict(threshold=5, positions=("start", "middle", "end"), mpg=20),
        "mid-season gaps only": dict(threshold=5, positions=("middle",), mpg=20),
        "long = 3+ games": dict(threshold=3, positions=("start", "middle", "end"), mpg=20),
        "long = 10+ games": dict(threshold=10, positions=("start", "middle", "end"), mpg=20),
        "starters only (28+ mpg)": dict(threshold=5, positions=("start", "middle", "end"), mpg=28),
    }
    res = {}
    for label, v in variants.items():
        pairs, halves = [], []
        for a, b in zip(bt.SEASONS, bt.SEASONS[1:]):
            for pid, x in tagged[a].items():
                y = tagged[b].get(pid)
                if not y or x["mpg"] < v["mpg"] or y["mpg"] < v["mpg"]:
                    continue
                qa, ma = q_of(x["gaps"], v["threshold"], v["positions"])
                qb, mb = q_of(y["gaps"], v["threshold"], v["positions"])
                if ma >= 5 and mb >= 5:
                    pairs.append((qa, qb))
        for s in bt.SEASONS:
            for pid, x in tagged[s].items():
                if x["mpg"] < v["mpg"]:
                    continue
                first = [g for g in x["gaps"] if g[2] < season_mid[s]]
                second = [g for g in x["gaps"] if g[2] >= season_mid[s]]
                q1, m1 = q_of(first, v["threshold"], v["positions"])
                q2, m2 = q_of(second, v["threshold"], v["positions"])
                if m1 >= 5 and m2 >= 5:
                    halves.append((q1, q2))
        r_yoy = float(np.corrcoef(np.array(pairs).T)[0, 1]) if len(pairs) > 10 else None
        r_half = float(np.corrcoef(np.array(halves).T)[0, 1]) if len(halves) > 10 else None
        # Spearman-Brown: reliability of a full season from the half-season correlation.
        rel = (2 * r_half / (1 + r_half)) if r_half and r_half > 0 else None
        res[label] = {"yoy_corr": r_yoy, "n_pairs": len(pairs), "split_half_corr": r_half, "n_halves": len(halves),
                      "full_season_reliability": rel,
                      "disattenuated_yoy": (r_yoy / rel) if (r_yoy is not None and rel) else None}
    return res


def main():
    pg, tg = bt.load()
    draft = bt.nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    cp = pd.concat([bt.checkpoint_rows(s, pg[s], tg[s]) for s in bt.TRAIN + bt.TEST], ignore_index=True)
    _, cp = bt.section_recent_form(cp)
    out = {}
    out.update(r1_r3(cp)); print("R1/R3 done", flush=True)
    out["R2"] = r2(cp); print("R2 done", flush=True)
    out.update(r4_r6(pg, hist)); print("R4/R6 done", flush=True)
    out["R5"] = r5(pg, tg); print("R5 done", flush=True)
    with open(OUT, "w") as f:
        json.dump(out, f, indent=2, default=float)


if __name__ == "__main__":
    main()
