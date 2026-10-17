"""Does a Cox proportional-hazards model of long absences improve BPV's availability estimate?

Run:  python -m analysis.test_cox        (writes analysis/test_cox.json)

Event: a player's first stretch of LONG+ straight missed team games in a season (from game
logs, so it covers injuries, suspensions and rest alike: whatever costs a fantasy manager).
Time: team games into the season. Players without one are censored at season end.
Covariates (all known before the season): age, height, weight, last season's minutes,
usage, games-played share and FPTS/game, BPV's current availability estimate, and the number
of long absences in earlier seasons.

For each target season 2022-23..2025-26 the model is fitted only on earlier seasons
(2020-21 on), then turned into an availability prediction two ways:
  bucket    risk quintile -> the median availability that quintile actually had in training
  combined  BPV's current estimate shifted by c x (risk - median risk), c tuned on training
Medians and absolute-error tuning are used because availability is lopsided (most regulars
play 85-95% of games, a few miss whole seasons), and the score is mean absolute error.
Both are compared with BPV's current estimate (recency-weighted, shrunk) on the same
953 player-seasons used in analysis/robustness.py (R6).
"""
import json
import os
import warnings
from bisect import bisect_left, bisect_right

import numpy as np
import pandas as pd
from lifelines import CoxPHFitter
from lifelines.statistics import proportional_hazard_test
from lifelines.utils import concordance_index

from analysis import backtest as bt
from analysis import robustness as rb
import bpv
import nba_data

warnings.filterwarnings("ignore")
LONG = int(os.environ.get("COX_LONG_ABSENCE", 10))
TARGETS = ["2022-23", "2023-24", "2024-25", "2025-26"]
COVARIATES = ["age", "height", "weight", "mpg_prev", "usg_prev", "avail_prev", "fpts_prev", "p_hat", "long_before"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_cox.json" if LONG == 10 else f"test_cox_{LONG}.json")
RNG = np.random.default_rng(9)


def first_long_absence(season_pg, season_tg, debut_ids):
    """player -> (event, time, season_length): time = team-game index when his first LONG+ absence began."""
    sched = {t: sorted(d) for t, d in season_tg.groupby("TEAM_ID").GAME_DATE}
    out = {}
    for pid, g in season_pg.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        app = list(zip(g.GAME_DATE, g.TEAM_ID))
        length = len(sched[app[-1][1]])
        starts = []                                    # (start index, gap length)
        d0, t0 = app[0]
        n0 = bisect_left(sched[t0], d0)
        if n0 and pid not in debut_ids:
            starts.append((0, n0))
        for (d1, t1), (d2, t2) in zip(app, app[1:]):
            c = lambda t: max(0, bisect_left(sched[t], d2) - bisect_right(sched[t], d1))
            n = c(t1) if t1 == t2 else min(c(t1), c(t2))
            if n:
                starts.append((bisect_right(sched[t1], d1), n))
        dl, tl = app[-1]
        n = len(sched[tl]) - bisect_right(sched[tl], dl)
        if n:
            starts.append((bisect_right(sched[tl], dl), n))
        long = [s for s, n in starts if n >= LONG]
        out[pid] = (1, min(long) + 1, length) if long else (0, length, length)
    return out


def build_rows(pg, tg, draft, hist):
    seasons = bt.SEASONS
    debuts = bpv.debut_ids(seasons, pg, draft)
    events = {s: first_long_absence(pg[s], tg[s], debuts[s]) for s in seasons}
    season_len = {s: int(tg[s].groupby("TEAM_ID").size().median()) for s in seasons}
    long_counts = {s: {pid: e[0] for pid, e in events[s].items()} for s in seasons}
    rows = []
    for i, target in enumerate(seasons[1:], 1):
        prev = seasons[i - 1]
        p_league, _ = rb.league_before(hist, target)
        p_hat = bpv.predict_availability(hist, seasons, prev, 0.5, 123, p_league)
        bio = nba_data.player_bio(prev).set_index("PLAYER_ID")
        h_prev = hist[(hist.season == prev) & (hist.mpg >= 20) & (hist.played >= 20)].set_index("PLAYER_ID")
        h_t = hist[hist.season == target].set_index("PLAYER_ID")
        for pid, hp in h_prev.iterrows():
            if pid not in bio.index or pid not in h_t.index:
                continue
            b = bio.loc[pid]
            if pd.isna(b.PLAYER_WEIGHT) or pd.isna(b.PLAYER_HEIGHT_INCHES):
                continue
            if pid in events[target]:
                event, time, _ = events[target][pid]
            else:                                          # missed the whole season
                event, time = 1, 1
            rows.append({
                "target": target, "PLAYER_ID": pid, "event": event, "time": time,
                "availability": float(h_t.loc[pid].availability),
                "age": float(b.AGE), "height": float(b.PLAYER_HEIGHT_INCHES), "weight": float(b.PLAYER_WEIGHT),
                "mpg_prev": float(hp.mpg), "usg_prev": float(b.USG_PCT), "avail_prev": float(hp.availability),
                "fpts_prev": float(hp.fpts_pg), "p_hat": float(p_hat.get(pid, p_league)),
                "long_before": sum(long_counts[s].get(pid, 0) for s in seasons[:i]),
            })
    return pd.DataFrame(rows)


def fit_cox(train):
    mu, sd = train[COVARIATES].mean(), train[COVARIATES].std()
    z = (train[COVARIATES] - mu) / sd
    cph = CoxPHFitter(penalizer=0.01)
    cph.fit(pd.concat([z, train[["time", "event"]]], axis=1), duration_col="time", event_col="event")
    return cph, mu, sd


def risk(cph, mu, sd, df):
    return np.log(cph.predict_partial_hazard((df[COVARIATES] - mu) / sd).to_numpy())


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    rows = build_rows(pg, tg, draft, hist)
    scored, per_target = [], {}
    for t in TARGETS:
        train = rows[rows.target.map(bt.SEASONS.index) < bt.SEASONS.index(t)].copy()
        test = rows[rows.target == t].copy()
        cph, mu, sd = fit_cox(train)
        train["risk"], test["risk"] = risk(cph, mu, sd, train), risk(cph, mu, sd, test)
        # Bucket calibration: risk quintile -> observed availability in training.
        edges = np.quantile(train.risk, [0.2, 0.4, 0.6, 0.8])
        train_q, test_q = np.digitize(train.risk, edges), np.digitize(test.risk, edges)
        bucket_avail = pd.Series(train.availability.values).groupby(train_q).median()
        test["p_cox"] = pd.Series(test_q).map(bucket_avail).to_numpy()
        # Combined: does the risk score add information beyond BPV's current estimate?
        centre = train.risk.median()
        shifts = np.round(np.arange(-0.10, 0.101, 0.005), 3)
        errs = {c: bt.mae(np.clip(train.p_hat + c * (train.risk - centre), 0, 1), train.availability) for c in shifts}
        best_c = min(errs, key=errs.get)
        coef = [float(best_c)]
        test["p_combined"] = np.clip(test.p_hat + best_c * (test.risk - centre), 0, 1)
        per_target[t] = {
            "n_train": len(train), "n_test": len(test), "events_test": int(test.event.sum()),
            "c_index_test": float(concordance_index(test.time, -test.risk, test.event)),
            "c_index_current_p_hat": float(concordance_index(test.time, test.p_hat, test.event)),
            "mae_current": bt.mae(test.p_hat, test.availability),
            "mae_cox_bucket": bt.mae(test.p_cox, test.availability),
            "mae_combined": bt.mae(test.p_combined, test.availability),
            "combined_shift_per_unit_risk": coef[0],
        }
        scored.append(test)
    df = pd.concat(scored, ignore_index=True)
    df["PLAYER_ID"] = df.PLAYER_ID.astype(str) + df.target

    def boot(a, b):
        e = (np.abs(df[a] - df.availability) - np.abs(df[b] - df.availability)).to_numpy()
        groups = df.groupby("PLAYER_ID").indices
        ids = list(groups)
        out = [e[np.concatenate([groups[ids[i]] for i in RNG.choice(len(ids), len(ids))])].mean() for _ in range(500)]
        return {"diff": float(e.mean()), "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]}

    # Final model on all seasons, for the report: hazard ratios per standard deviation, and the PH test.
    cph, mu, sd = fit_cox(rows)
    z = (rows[COVARIATES] - mu) / sd
    ph = proportional_hazard_test(cph, pd.concat([z, rows[["time", "event"]]], axis=1), time_transform="rank")
    summary = cph.summary[["exp(coef)", "exp(coef) lower 95%", "exp(coef) upper 95%", "p"]]
    res = {
        "long_absence_games": LONG, "n_rows_total": len(rows), "event_rate": float(rows.event.mean()),
        "per_target": per_target,
        "pooled": {"n": len(df), "mae_current": bt.mae(df.p_hat, df.availability),
                   "mae_cox_bucket": bt.mae(df.p_cox, df.availability),
                   "mae_combined": bt.mae(df.p_combined, df.availability),
                   "cox_bucket_minus_current": boot("p_cox", "p_hat"),
                   "combined_minus_current": boot("p_combined", "p_hat")},
        "hazard_ratios_per_sd": {k: {"hr": float(v["exp(coef)"]), "lo": float(v["exp(coef) lower 95%"]),
                                     "hi": float(v["exp(coef) upper 95%"]), "p": float(v["p"])}
                                 for k, v in summary.iterrows()},
        "ph_test_p": {k: float(v) for k, v in ph.summary["p"].items()},
        "covariate_sd": {k: float(v) for k, v in sd.items()},
    }
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2)
    print(json.dumps({k: v for k, v in res.items() if k != "covariate_sd"}, indent=1))


if __name__ == "__main__":
    main()
