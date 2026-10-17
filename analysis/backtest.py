"""Backtests that choose BPV's constants from real data.

Run:  python -m analysis.backtest            (writes analysis/results.json)

Sections
  A. Recent form: which recency weight (the paper's 20%) best predicts the
     rest of the season, and is it minutes or efficiency that carries over?
  B. New Role Value: for players whose minutes jumped, test the 90% haircut
     and the 50/50 blend.
  C. Availability: how to estimate next season's games-played share from
     history (recency decay, shrinkage k), and whether "erratic vs long"
     absence patterns persist from year to year.
  D. Rookies and early season: draft-slot baselines and how many games of
     real data it takes to outweigh them.
  E. Preseason model comparison: the paper's Models 1/2/3/5 vs the
     replacement-level BPV, scored by rank correlation and simulated drafts.
"""
import datetime as dt
import json
import os
import random
import sys
from bisect import bisect_left
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import bpv  # noqa: E402
import nba_data  # noqa: E402

# Last season to include; raise it (e.g. BACKTEST_LAST_SEASON=2026) once a new season is complete.
LAST_SEASON = int(os.environ.get("BACKTEST_LAST_SEASON", 2025))
SEASONS = [nba_data.season_string(y) for y in range(2019, LAST_SEASON + 1)]
TRAIN = ["2021-22", "2022-23", "2023-24", "2024-25"]
TEST = ["2025-26"]
RECENT_GAMES = 5
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results.json")


def load():
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in SEASONS}
    tg = {s: nba_data.team_game_logs(s) for s in SEASONS}
    return pg, tg


def mae(pred, actual):
    return float(np.mean(np.abs(np.asarray(pred) - np.asarray(actual))))


def spearman(a, b):
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


# ---------------------------------------------------------------- checkpoints
def checkpoints(season_pg, first_offset_days, step_days=7, stop_before_end_days=21):
    dates = sorted(season_pg["GAME_DATE"].unique())
    start = dt.date.fromisoformat(dates[0]) + dt.timedelta(days=first_offset_days)
    end = dt.date.fromisoformat(dates[-1]) - dt.timedelta(days=stop_before_end_days)
    out = []
    while start <= end:
        out.append(start.isoformat())
        start += dt.timedelta(days=step_days)
    return out


def checkpoint_rows(season, season_pg, season_tg, first_offset_days=28, min_before=10, min_after=10):
    """One row per (player, checkpoint) with what was known then and what happened after."""
    schedules = {t: sorted(d) for t, d in season_tg.groupby("TEAM_ID")["GAME_DATE"]}
    cps = checkpoints(season_pg, first_offset_days)
    rows = []
    for pid, g in season_pg.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        dates = g["GAME_DATE"].tolist()
        fp = g["FPTS"].to_numpy(float)
        mins = g["MIN"].to_numpy(float)
        teams = g["TEAM_ID"].tolist()
        for c in cps:
            i = bisect_left(dates, c)
            if i < min_before or len(dates) - i < min_after:
                continue
            s_fp, s_min = fp[:i].mean(), mins[:i].mean()
            r = slice(max(0, i - RECENT_GAMES), i)
            l_fp, l_min = fp[r].mean(), mins[r].mean()
            # The paper's definition: the team's last 5 games, averaging only those he played.
            sched = schedules[teams[i - 1]]
            j = bisect_left(sched, c)
            window = set(sched[max(0, j - RECENT_GAMES):j])
            in_window = [k for k in range(i) if dates[k] in window]
            t5_fp = fp[in_window].mean() if in_window else np.nan
            next_end = (dt.date.fromisoformat(c) + dt.timedelta(days=14)).isoformat()
            nxt = [k for k in range(i, len(dates)) if dates[k] < next_end]
            rows.append({
                "season": season, "checkpoint": c, "PLAYER_ID": pid,
                "n_before": i, "S": s_fp, "L5": l_fp, "T5": t5_fp, "t5_games": len(in_window),
                "mpg_S": s_min, "mpg_L5": l_min,
                "A_ros": fp[i:].mean(), "A_next14": fp[nxt].mean() if len(nxt) >= 2 else np.nan,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- A. recent form
def section_recent_form(cp):
    res = {}
    cp = cp[cp["mpg_S"] >= 12].copy()
    cp["T5f"] = cp["T5"].fillna(cp["S"])
    cp["fpm_S"] = cp["S"] / cp["mpg_S"].clip(lower=1)
    cp["min_model"] = cp["fpm_S"] * cp["mpg_L5"]
    weights = np.round(np.arange(0, 0.61, 0.05), 2)

    for target in ["A_ros", "A_next14"]:
        tr = cp[cp.season.isin(TRAIN)].dropna(subset=[target])
        te = cp[cp.season.isin(TEST)].dropna(subset=[target])
        block = {}
        for label, recent in [("last5_played", "L5"), ("team_last5", "T5f")]:
            grid = {float(w): mae((1 - w) * tr.S + w * tr[recent], tr[target]) for w in weights}
            best = min(grid, key=grid.get)
            d, y = tr[recent] - tr.S, tr[target] - tr.S
            closed = float((d * y).sum() / (d * d).sum())
            block[label] = {
                "train_mae_by_weight": grid, "best_weight": best, "closed_form_weight": closed,
                "test_mae_season_only": mae(te.S, te[target]),
                "test_mae_paper_20pct": mae(0.8 * te.S + 0.2 * te[recent], te[target]),
                "test_mae_best_weight": mae((1 - best) * te.S + best * te[recent], te[target]),
            }
        # Split the recent change into a minutes part and an efficiency part.
        d_min = tr.fpm_S * (tr.mpg_L5 - tr.mpg_S)
        d_rate = tr.L5 - tr.S - d_min
        X = np.column_stack([d_min, d_rate])
        coef, *_ = np.linalg.lstsq(X, (tr[target] - tr.S).to_numpy(), rcond=None)
        te_dmin = te.fpm_S * (te.mpg_L5 - te.mpg_S)
        te_drate = te.L5 - te.S - te_dmin
        block["minutes_vs_efficiency"] = {
            "weight_on_minutes_change": float(coef[0]), "weight_on_efficiency_change": float(coef[1]),
            "test_mae": mae(te.S + coef[0] * te_dmin + coef[1] * te_drate, te[target]),
        }
        block["n_train"], block["n_test"] = len(tr), len(te)
        res[target] = block
    return res, cp


# ---------------------------------------------------------------- B. new role
def section_new_role(cp):
    role = cp[(cp.mpg_L5 - cp.mpg_S >= 8) & (cp.mpg_S <= 24)].dropna(subset=["A_ros"]).copy()
    role["M2"] = 0.8 * role.S + 0.2 * role.L5
    tr, te = role[role.season.isin(TRAIN)], role[role.season.isin(TEST)]

    def paper(df, haircut=0.9, blend=0.5):
        return (1 - blend) * df.M2 + blend * df.fpm_S * df.mpg_L5 * haircut

    grid = {(h, b): mae(paper(tr, h, b), tr.A_ros)
            for h in np.round(np.arange(0.6, 1.11, 0.05), 2) for b in np.round(np.arange(0, 1.01, 0.1), 1)}
    (bh, bb) = min(grid, key=grid.get)
    return {
        "n_train": len(tr), "n_test": len(te),
        "definition": "last-5 minutes at least 8 above season-to-date, season-to-date at most 24",
        "avg_minutes_before": float(role.mpg_S.mean()), "avg_minutes_last5": float(role.mpg_L5.mean()),
        "test_mae": {
            "season_only (Model 1)": mae(te.S, te.A_ros),
            "80/20 (Model 2)": mae(te.M2, te.A_ros),
            "paper NRV: 90% haircut, 50/50": mae(paper(te), te.A_ros),
            f"fitted: {bh:.2f} haircut, {bb:.1f} on new role": mae(paper(te, bh, bb), te.A_ros),
        },
        "best_haircut": float(bh), "best_new_role_weight": float(bb),
    }


# ---------------------------------------------------------------- C. availability
def availability_history(pg, tg, draft):
    hist = bpv.availability_history(SEASONS, pg, tg, draft)
    return hist, int(((hist.played == 0) & (hist.mpg == 0)).sum())


def predict_availability(hist, target, decay, k, prior):
    """Availability for `target` predicted from the seasons before it."""
    return bpv.predict_availability(hist, SEASONS, SEASONS[SEASONS.index(target) - 1], decay, k, prior)


def section_availability(hist):
    res = {}
    relevant_prev = lambda s: set(hist[(hist.season == s) & (hist.mpg >= 20) & (hist.played >= 20)].PLAYER_ID)
    league_p, league_q = bpv.league_availability(hist)
    targets = SEASONS[2:]
    evals = []
    for decays in [(1.0,), (0.0001,), (0.5,), (0.7,), (0.85,)]:
        for k in [0, 20, 41, 82, 123, 164]:
            errs = []
            for t in targets:
                ids = relevant_prev(SEASONS[SEASONS.index(t) - 1])
                actual = hist[(hist.season == t) & hist.PLAYER_ID.isin(ids)].set_index("PLAYER_ID").availability
                pred = predict_availability(hist, t, decays[0], k, league_p).reindex(actual.index)
                errs.append(mae(pred, actual))
            evals.append({"decay": decays[0], "k": k, "mae": float(np.mean(errs))})
    best = min(evals, key=lambda e: e["mae"])
    # Paper's career GP% (all prior seasons equally weighted, no shrinkage) and a naive 100%.
    errs_paper, errs_last, errs_flat = [], [], []
    for t in targets:
        ids = relevant_prev(SEASONS[SEASONS.index(t) - 1])
        actual = hist[(hist.season == t) & hist.PLAYER_ID.isin(ids)].set_index("PLAYER_ID").availability
        errs_paper.append(mae(predict_availability(hist, t, 1.0, 0, league_p).reindex(actual.index), actual))
        errs_last.append(mae(predict_availability(hist, t, 0.0001, 0, league_p).reindex(actual.index), actual))
        errs_flat.append(mae(np.full(len(actual), league_p), actual))
    res["league_availability_mpg20"] = league_p
    res["grid"] = evals
    res["best"] = best
    res["mae_career_gp_pct_like_paper"] = float(np.mean(errs_paper))
    res["mae_last_season_only"] = float(np.mean(errs_last))
    res["mae_everyone_league_average"] = float(np.mean(errs_flat))

    # Do absence patterns persist? Year-over-year correlation among relevant players.
    rel = hist[(hist.mpg >= 20) | (hist.played == 0)]
    pairs_p, pairs_q = [], []
    for a, b in zip(SEASONS, SEASONS[1:]):
        x = rel[rel.season == a].set_index("PLAYER_ID")
        y = rel[rel.season == b].set_index("PLAYER_ID")
        both = x.index.intersection(y.index)
        pairs_p += list(zip(x.loc[both].availability, y.loc[both].availability))
        m = [(x.loc[i].manageable, y.loc[i].manageable) for i in both
             if x.loc[i].missed >= 5 and y.loc[i].missed >= 5]
        pairs_q += m
    res["yoy_corr_availability"] = float(np.corrcoef(np.array(pairs_p).T)[0, 1])
    res["yoy_corr_manageable"] = float(np.corrcoef(np.array(pairs_q).T)[0, 1])
    res["n_pairs_manageable"] = len(pairs_q)
    res["league_manageable_share"] = league_q
    return res, league_p, league_q


# ---------------------------------------------------------------- D. rookies / early season
pick_bucket = bpv.pick_bucket
bucket_baselines = bpv.rookie_baselines


def rookie_table(pg, draft, hist):
    return bpv.rookie_seasons(SEASONS, pg, draft, hist)


def section_early_season(pg, tg, draft, hist):
    rt = rookie_table(pg, draft, hist)
    res = {"rookie_baselines": bucket_baselines(rt)}
    picks = draft.set_index("PERSON_ID").OVERALL_PICK
    rookie_k, vet_k = defaultdict(list), defaultdict(list)
    ks = [0, 2, 4, 6, 8, 10, 15, 20, 30]
    for s in SEASONS[2:]:
        base = bucket_baselines(rt[rt.season != s])          # leave the tested season out
        cp = checkpoint_rows(s, pg[s], tg[s], first_offset_days=7, min_before=1, min_after=10)
        cp = cp[cp.n_before <= 20]
        rookies = set(rt[rt.season == s].PLAYER_ID)
        prev = hist[(hist.season == SEASONS[SEASONS.index(s) - 1])].set_index("PLAYER_ID")
        for _, r in cp.iterrows():
            if r.PLAYER_ID in rookies:
                prior = base[pick_bucket(picks.get(r.PLAYER_ID))]["fpts_per_game"]
                for k in ks:
                    rookie_k[k].append(abs(bpv.shrink(r.S, r.n_before, prior, k) - r.A_ros))
            elif r.PLAYER_ID in prev.index and prev.loc[r.PLAYER_ID].played >= 20:
                prior = prev.loc[r.PLAYER_ID].fpts_pg
                for k in ks:
                    vet_k[k].append(abs(bpv.shrink(r.S, r.n_before, prior, k) - r.A_ros))
    res["rookie_mae_by_k"] = {k: float(np.mean(v)) for k, v in rookie_k.items()}
    res["returning_player_mae_by_k"] = {k: float(np.mean(v)) for k, v in vet_k.items()}
    res["rookie_best_k"] = min(res["rookie_mae_by_k"], key=res["rookie_mae_by_k"].get)
    res["returning_player_best_k"] = min(res["returning_player_mae_by_k"], key=res["returning_player_mae_by_k"].get)
    res["n_rookie_obs"], res["n_returning_obs"] = len(rookie_k[0]), len(vet_k[0])
    return res


# ---------------------------------------------------------------- E. preseason model comparison
def age_curve_before(pg, target, min_games=20, min_mpg=15):
    """Average change in FPTS/game from one season to the next, by age bucket, using only seasons before `target`."""
    rows = []
    for a, b in zip(SEASONS, SEASONS[1:SEASONS.index(target)]):
        x = pg[a].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), gp=("FPTS", "size"), mpg=("MIN", "mean"))
        y = pg[b].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), gp=("FPTS", "size"))
        ages = nba_data.player_ages(a).set_index("PLAYER_ID")["AGE"]
        x = x[(x.gp >= min_games) & (x.mpg >= min_mpg)]
        ids = x.index.intersection(y[y.gp >= min_games].index).intersection(ages.index)
        rows.append(pd.DataFrame({"bucket": ages.loc[ids].map(bpv.age_bucket), "change": y.fp.loc[ids] - x.fp.loc[ids]}))
    d = pd.concat(rows)
    return d.groupby("bucket").change.mean().to_dict()


def preseason_frame(pg, hist, target, avail_decay, avail_k, league_p, league_q, replacement_rank=130, age_curve=None):
    prev = SEASONS[SEASONS.index(target) - 1]
    h_prev = hist[(hist.season == prev) & (hist.played >= 20)].set_index("PLAYER_ID")
    last5 = (pg[prev].sort_values("GAME_DATE").groupby("PLAYER_ID").tail(RECENT_GAMES)
             .groupby("PLAYER_ID").FPTS.mean())
    career_p = predict_availability(hist, target, 1.0, 0, league_p)
    p_hat = predict_availability(hist, target, avail_decay, avail_k, league_p)
    use = hist[hist.season.map(SEASONS.index) < SEASONS.index(target)]
    q_g = use.groupby("PLAYER_ID")[["missed_long", "missed"]].sum()
    q_hat = bpv.shrink(q_g.missed_long / q_g.missed.clip(lower=1e-9), q_g.missed, league_q, 20)
    R = bpv.replacement_level(h_prev.fpts_pg, replacement_rank)

    df = pd.DataFrame({"S": h_prev.fpts_pg, "L5": last5.reindex(h_prev.index),
                       "career_p": career_p.reindex(h_prev.index), "p_hat": p_hat.reindex(h_prev.index),
                       "q_hat": q_hat.reindex(h_prev.index).fillna(league_q), "total_prev": h_prev.fpts_total})
    df["M1 season FPTS"] = df.S
    df["M2 80/20"] = 0.8 * df.S + 0.2 * df.L5
    df["M3 x career GP%"] = df.S * df.career_p
    df["M5 80/20 x career GP%"] = df["M2 80/20"] * df.career_p
    # q is the league average, as in the app (one player's pattern is too noisy to measure).
    df["BPV (replacement-level)"] = bpv.bpv_value(df.S, df.p_hat, league_q, R)
    if age_curve is not None:
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID")["AGE"].reindex(df.index)
        eligible = (h_prev.mpg.reindex(df.index) >= 15) & ages.notna()
        adj = ages.map(lambda a: age_curve.get(bpv.age_bucket(a), 0.0) if pd.notna(a) else 0.0).where(eligible, 0.0)
        df["BPV + age"] = bpv.bpv_value(df.S + adj, df.p_hat, league_q, R)
    df["Last season total FPTS"] = df.total_prev

    h_t = hist[hist.season == target].set_index("PLAYER_ID")
    later = set(hist[hist.season.map(SEASONS.index) > SEASONS.index(target)].PLAYER_ID)
    keep = df.index.isin(h_t.index) | df.index.isin(later)        # drop retirements
    df = df[keep].copy()
    df["actual_total"] = h_t.fpts_total.reindex(df.index).fillna(0)
    R_t = bpv.replacement_level(hist[(hist.season == target) & (hist.played >= 20)].fpts_pg, replacement_rank)
    df["actual_managed"] = df.actual_total + R_t * h_t.missed_long.reindex(df.index).fillna(0)
    return df, R


MODELS = ["M1 season FPTS", "M2 80/20", "M3 x career GP%", "M5 80/20 x career GP%",
          "BPV (replacement-level)", "BPV + age", "Last season total FPTS"]


def simulate_drafts(df, strategies, n_sims=1000, teams=10, rounds=13, seed=7, target="actual_total"):
    rng = random.Random(seed)
    rankings = {s: df[s].sort_values(ascending=False).index.tolist() for s in strategies}
    seats = [s for s in strategies for _ in range(teams // len(strategies))]
    totals = defaultdict(list)
    actual = df[target].to_dict()
    for _ in range(n_sims):
        order = seats[:]
        rng.shuffle(order)
        taken, rosters = set(), defaultdict(list)
        pos = {s: 0 for s in strategies}
        for rnd in range(rounds):
            seq = range(teams) if rnd % 2 == 0 else range(teams - 1, -1, -1)
            for seat in seq:
                strat = order[seat]
                ranking = rankings[strat]
                i = 0
                while ranking[i] in taken:
                    i += 1
                taken.add(ranking[i])
                rosters[seat].append(ranking[i])
        for seat, roster in rosters.items():
            totals[order[seat]].append(sum(actual[p] for p in roster))
    return {s: {"mean": float(np.mean(v)), "sd": float(np.std(v))} for s, v in totals.items()}


def section_models(pg, hist, avail, league_p, league_q):
    res = {}
    for target in SEASONS[3:]:
        df, R = preseason_frame(pg, hist, target, avail["best"]["decay"], avail["best"]["k"], league_p, league_q,
                                age_curve=age_curve_before(pg, target))
        pool = df[df.S >= 15]
        block = {"replacement_level_prev_season": R, "players": len(pool),
                 "spearman_vs_actual_total": {m: spearman(pool[m], pool.actual_total) for m in MODELS},
                 "spearman_vs_actual_managed": {m: spearman(pool[m], pool.actual_managed) for m in MODELS}}
        strategies = ["M3 x career GP%", "M5 80/20 x career GP%", "BPV (replacement-level)", "BPV + age",
                      "Last season total FPTS"]
        block["draft_sim_total"] = simulate_drafts(df.dropna(subset=strategies), strategies)
        block["draft_sim_managed"] = simulate_drafts(df.dropna(subset=strategies), strategies, target="actual_managed")
        res[target] = block
    return res


def main():
    pg, tg = load()
    draft = nba_data.draft_history()
    results = {}

    cp = pd.concat([checkpoint_rows(s, pg[s], tg[s]) for s in TRAIN + TEST], ignore_index=True)
    results["A_recent_form"], cp = section_recent_form(cp)
    print("A done", flush=True)
    results["B_new_role"] = section_new_role(cp)
    print("B done", flush=True)

    hist, n_absent = availability_history(pg, tg, draft)
    avail, league_p, league_q = section_availability(hist)
    avail["whole_seasons_missed_added"] = n_absent
    results["C_availability"] = avail
    print("C done", flush=True)

    results["D_early_season"] = section_early_season(pg, tg, draft, hist)
    print("D done", flush=True)
    results["E_models"] = section_models(pg, hist, avail, league_p, league_q)
    print("E done", flush=True)

    with open(OUT, "w") as f:
        json.dump(results, f, indent=2, default=float)
    print(json.dumps(results, indent=1, default=float)[:200])


if __name__ == "__main__":
    main()
