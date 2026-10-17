"""Two candidate improvements: coaching changes (preseason) and weekly consistency (head-to-head).

Run:  python -m analysis.test_coach_consistency     (prints results as JSON)

TEST 1  Coaching changes. Head coach per team-season from CommonTeamRoster (cached in
        data/cache/head_coaches_<season>.csv; the endpoint lists the coach on the staff at the end of
        the season, so a mid-season interim who kept the job counts as that season's coach).
        Minutes concentration of a team-season = share of team minutes played by its top 5 players.
        A coach's concentration = his team's in his most recent earlier season as head coach
        (any team, data from 2019-20 on), else the league average.
        For target season T, a team has a new coach if its T head coach differs from T-1.
        delta = new coach's concentration - the team's T-1 concentration.
        Candidate terms added to the current preseason projection
        (last FPTS/g + age curve + CROWDING_COEF x crowding), each coefficient fitted leave-one-season-out:
          signed      new x delta x (+1 if among his new team's top-5 in last-season mpg, else -1)
          minutes     new x FPTS/g x expected relative minutes change
                      (top-5: delta / old_conc, others: -delta / (1 - old_conc))
          new_coach   new-coach indicator (intercept shift)
        Also: are errors larger for players on new-coach teams?
TEST 2  Weekly consistency. Mon-Sun weekly fantasy totals, per-game FPTS SD / CV for 20+ mpg players.
        (a) year-to-year stability of CV; (b) simulated 10-player head-to-head teams (2024-25, 2025-26).
Every CI is a 95% cluster bootstrap that resamples players.
"""
import json
import os
import time
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp
from analysis import test_minutes_model as tmm
from analysis.test_misc import boot, verdict
import nba_data

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(55)
CROWDING_COEF = -0.0177     # as in ratings.py


# ================================================================ data: head coaches
def head_coaches(season, team_ids):
    path = os.path.join(nba_data.CACHE_DIR, f"head_coaches_{season}.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    from nba_api.stats.endpoints import CommonTeamRoster
    rows = []
    for tid in team_ids:
        for attempt in range(4):
            try:
                c = CommonTeamRoster(team_id=int(tid), season=season, timeout=60).get_data_frames()[1]
                break
            except Exception:
                time.sleep(3 * (attempt + 1))
        else:
            raise RuntimeError(f"coach fetch failed {tid} {season}")
        h = c[c.COACH_TYPE == "Head Coach"]
        if h.empty:
            rows.append({"TEAM_ID": int(tid), "SEASON": season, "COACH_ID": np.nan, "COACH_NAME": None, "N_HEAD": 0})
        else:
            rows.append({"TEAM_ID": int(tid), "SEASON": season, "COACH_ID": int(h.COACH_ID.iloc[0]),
                         "COACH_NAME": h.COACH_NAME.iloc[0], "N_HEAD": len(h)})
        time.sleep(1.0)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False)
    return df


# CommonTeamRoster's coach list for season s is a snapshot taken after s ended (e.g. its "2019-20" list
# already has Nash, Lue, Silas, Thibodeau, hired in the 2020 offseason). So the coach who OPENED season s
# is read from the list for s-1, falling back to the list for s when that team has no head coach listed.
# Checked by hand against the public record for every team 2019-20..2025-26; four openers the snapshot
# gets wrong (hired after it was taken, or an interim who kept the job) are corrected here.
OPENING_FIXES = {("2022-23", "BOS"): "Joe Mazzulla", ("2022-23", "UTA"): "Will Hardy",
                 ("2024-25", "CHA"): "Charles Lee", ("2024-25", "CLE"): "Kenny Atkinson"}


def all_coaches(tg):
    team_ids = sorted(tg[bt.SEASONS[0]].TEAM_ID.unique())
    listed = pd.concat([head_coaches(s, team_ids)
                        for s in [nba_data.previous_season(bt.SEASONS[0])] + bt.SEASONS], ignore_index=True)
    abbr = tg[bt.SEASONS[-1]].drop_duplicates("TEAM_ID").set_index("TEAM_ID").TEAM_ABBREVIATION
    ids = listed.dropna(subset=["COACH_ID"]).drop_duplicates("COACH_NAME").set_index("COACH_NAME").COACH_ID
    lst = listed.set_index(["TEAM_ID", "SEASON"]).COACH_NAME
    rows = []
    for s in bt.SEASONS:
        prev = nba_data.previous_season(s)
        for tid in abbr.index:
            name = lst.get((tid, prev))
            if not isinstance(name, str):
                name = lst.get((tid, s))
            fixed = OPENING_FIXES.get((s, abbr[tid]))
            rows.append({"TEAM_ID": tid, "TEAM": abbr[tid], "SEASON": s, "COACH_NAME": fixed or name,
                         "COACH_ID": ids.get(fixed or name, np.nan), "fixed": fixed is not None})
    return pd.DataFrame(rows)


# ================================================================ TEST 1
def concentration(season_pg):
    m = season_pg.groupby(["TEAM_ID", "PLAYER_ID"]).MIN.sum()
    return m.groupby(level=0).apply(lambda x: x.nlargest(5).sum() / x.sum())


def test1(pg, tg):
    coaches = all_coaches(tg)
    coach = {(r.TEAM_ID, r.SEASON): r.COACH_ID for r in coaches.itertuples()}
    coaches_name = {(r.TEAM_ID, r.SEASON): f"{r.TEAM} {r.COACH_NAME}" for r in coaches.itertuples()}
    conc = {s: concentration(pg[s]) for s in bt.SEASONS}
    tab = pp.season_table(pg)
    frames, changes = {}, []
    for t in pp.TARGETS:
        i = bt.SEASONS.index(t)
        prev = bt.SEASONS[i - 1]
        league = float(conc[prev].mean())
        team_info = {}
        for tid in conc[prev].index:
            c_new, c_old = coach.get((tid, t)), coach.get((tid, prev))
            new = bool(pd.notna(c_new) and pd.notna(c_old) and c_new != c_old)
            hist = None
            if new:
                for s in reversed(bt.SEASONS[:i]):
                    hit = coaches[(coaches.SEASON == s) & (coaches.COACH_ID == c_new)]
                    if len(hit):
                        hist = float(conc[s][hit.TEAM_ID.iloc[0]])
                        break
            old = float(conc[prev][tid])
            new_conc = hist if hist is not None else league
            team_info[tid] = {"new": new, "old_conc": old, "delta": (new_conc - old) if new else 0.0,
                              "known_history": hist is not None}
            if new:
                changes.append({"target": t, "TEAM_ID": int(tid),
                                "old_coach": coaches_name.get((tid, prev)), "new_coach": coaches_name.get((tid, t)), "old_conc": old, "new_coach_conc": new_conc,
                                "known_history": hist is not None,
                                "actual_T_conc": float(conc[t].get(tid, np.nan))})
        f = pp.frame(tab, t)
        ctx = tmm.roster_context(pg, t)
        prev_mpg = pg[prev].groupby("PLAYER_ID").MIN.mean()
        ctx["prev_mpg"] = prev_mpg.reindex(ctx.index).fillna(0)
        ctx["rank"] = ctx.groupby("team").prev_mpg.rank(ascending=False, method="first")
        f = f.merge(ctx[["crowding", "team", "rank"]], left_on="PLAYER_ID", right_index=True, how="left")
        f["crowding"] = f.crowding.fillna(0)
        info = f.team.map(lambda x: team_info.get(x, {"new": False, "old_conc": league, "delta": 0.0}))
        f["new"] = info.map(lambda d: float(d["new"]))
        f["delta"] = info.map(lambda d: d["delta"])
        f["old_conc"] = info.map(lambda d: d["old_conc"])
        f["top5"] = (f["rank"] <= 5).astype(float)
        sign = np.where(f.top5 == 1, 1.0, -1.0)
        f["signed"] = f.new * f.delta * sign
        rel = np.where(f.top5 == 1, f.delta / f.old_conc, -f.delta / (1 - f.old_conc))
        f["minutes"] = f.new * f.fp1 * rel
        f["new_coach"] = f.new
        frames[t] = f
    ch = pd.DataFrame(changes)
    # Sanity: does a new coach's past concentration predict the team's actual concentration change?
    ch["pred_change"] = ch.new_coach_conc - ch.old_conc
    ch["actual_change"] = ch.actual_T_conc - ch.old_conc
    known = ch[ch.known_history]
    res = {"n_team_seasons_new_coach": len(ch), "n_with_known_history": int(ch.known_history.sum()),
           "league_top5_share_mean": float(np.mean([conc[s].mean() for s in bt.SEASONS])),
           "corr_pred_vs_actual_conc_change_known": float(known.pred_change.corr(known.actual_change)) if len(known) > 2 else None,
           "slope_actual_on_pred_conc_change_known": float(np.polyfit(known.pred_change, known.actual_change, 1)[0]) if len(known) > 2 else None,
           "corr_pred_vs_actual_all": float(ch.pred_change.corr(ch.actual_change))}
    # Sanity: regression to the mean alone (league average - old concentration) on the same teams.
    lg = {t: float(conc[bt.SEASONS[bt.SEASONS.index(t) - 1]].mean()) for t in pp.TARGETS}
    naive = ch.target.map(lg) - ch.old_conc
    res["corr_naive_regression_to_mean_known"] = float(naive[ch.known_history].corr(known.actual_change))
    res["corr_naive_regression_to_mean_all"] = float(naive.corr(ch.actual_change))
    X = np.column_stack([np.ones(len(known)), naive[ch.known_history], known.pred_change - naive[ch.known_history]])
    res["known_history_coach_style_coef_beyond_regression"] = float(np.linalg.lstsq(X, known.actual_change, rcond=None)[0][2])
    res["new_coach_changes"] = ch.round(3).to_dict("records")
    scored, coefs = [], {k: [] for k in ("signed", "minutes", "new_coach")}
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        tr["last"], te["last"] = tr.fp1, te.fp1
        curve = pp.fit_age_curve(tr, "last")
        for d in (tr, te):
            d["base"] = pp.with_age(d, "last", curve) + CROWDING_COEF * d.crowding
        r = tr.actual - tr.base
        for k in coefs:
            x = tr[k]
            b = float((x * r).sum() / (x ** 2).sum())
            coefs[k].append(b)
            te[k + "_pred"] = te.base + b * te[k]
        scored.append(te)
    d = pd.concat(scored, ignore_index=True)
    err0 = np.abs(d.base - d.actual)
    res["n_players"] = len(d)
    res["n_players_new_coach_team"] = int(d.new.sum())
    res["mae_current"] = float(err0.mean())
    for k in coefs:
        e1 = np.abs(d[k + "_pred"] - d.actual)
        b = boot(d, e1, err0)
        sub = d.new == 1
        bs = boot(d[sub].reset_index(drop=True), e1[sub].to_numpy(), err0[sub].to_numpy())
        res[k] = {"coef_by_fold": coefs[k], "mae": float(e1.mean()), "minus_current": b, "verdict": verdict(b),
                  "new_coach_players_only": bs, "verdict_new_coach_players": verdict(bs)}
    # Uncertainty: absolute error on new-coach teams vs others.
    d["abs_err"] = err0
    d["rel_err"] = err0 / d.fp1.clip(lower=5)
    d["resid"] = d.actual - d.base
    for label, mask in [("all", np.ones(len(d), bool)), ("stayed_same_team", ~tmm_changed(d, pg))]:
        sub = d[mask].reset_index(drop=True)
        is_new = sub.new == 1
        out = {"n_new": int(is_new.sum()), "n_other": int((~is_new).sum()),
               "mae_new": float(sub.abs_err[is_new].mean()), "mae_other": float(sub.abs_err[~is_new].mean()),
               "mean_resid_new": float(sub.resid[is_new].mean()), "mean_resid_other": float(sub.resid[~is_new].mean())}
        out["abs_err_diff"] = group_diff_boot(sub, "abs_err", is_new)
        out["rel_err_diff"] = group_diff_boot(sub, "rel_err", is_new)
        res["uncertainty_" + label] = out
    return res


def tmm_changed(d, pg):
    """Did the player start the target season on a different team than he ended the prior one?"""
    out = np.zeros(len(d), bool)
    for t in pp.TARGETS:
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        last_team = pg[prev].sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
        m = (d.target == t).to_numpy()
        out[m] = (d.team[m].to_numpy() != last_team.reindex(d.PLAYER_ID[m]).to_numpy())
    return out


def group_diff_boot(df, col, mask, n=1000):
    """Mean(col | mask) - mean(col | ~mask), clustered bootstrap over players."""
    vals, m = df[col].to_numpy(), np.asarray(mask)
    groups = pd.Series(range(len(df))).groupby(df.PLAYER_ID.astype(str).to_numpy()).indices
    ids = list(groups)
    out = []
    for _ in range(n):
        idx = np.concatenate([groups[ids[i]] for i in RNG.choice(len(ids), len(ids))])
        out.append(vals[idx][m[idx]].mean() - vals[idx][~m[idx]].mean())
    diff = float(vals[m].mean() - vals[~m].mean())
    return {"diff": diff, "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]}


# ================================================================ TEST 2
def week_start(dates):
    d = pd.to_datetime(dates)
    return (d - pd.to_timedelta(d.dt.weekday, unit="D")).dt.strftime("%Y-%m-%d")


def player_season_stats(g):
    t = g.groupby("PLAYER_ID").agg(gp=("FPTS", "size"), mpg=("MIN", "mean"), fp=("FPTS", "mean"), sd=("FPTS", "std"))
    t["cv"] = t.sd / t.fp
    return t


def full_weeks(g):
    wk = week_start(g.GAME_DATE)
    games_per_week = g.assign(W=wk.values).groupby("W").GAME_ID.nunique()
    return sorted(games_per_week[games_per_week >= 0.6 * games_per_week.median()].index)


def weekly_matrix(g, pids, weeks):
    wk = week_start(g.GAME_DATE)
    w = g.assign(W=wk.values).groupby(["PLAYER_ID", "W"]).FPTS.sum().unstack().reindex(index=pids, columns=weeks)
    return w


def stability(pg):
    tabs = {s: player_season_stats(pg[s]) for s in bt.SEASONS}
    rows = []
    for a, b in zip(bt.SEASONS[:-1], bt.SEASONS[1:]):
        x, y = tabs[a], tabs[b]
        x, y = x[(x.mpg >= 20) & (x.gp >= 20)], y[(y.mpg >= 20) & (y.gp >= 20)]
        ids = x.index.intersection(y.index)
        rows.append(pd.DataFrame({"PLAYER_ID": ids, "pair": f"{a}->{b}", "cv1": x.cv[ids].values, "cv2": y.cv[ids].values,
                                  "fp1": x.fp[ids].values, "fp2": y.fp[ids].values,
                                  "sd1": x.sd[ids].values, "sd2": y.sd[ids].values}))
    d = pd.concat(rows, ignore_index=True)
    # CV mechanically falls with the mean; residualize CV on log(mean) within each season.
    for k in ("1", "2"):
        X = np.column_stack([np.ones(len(d)), np.log(d["fp" + k])])
        coef, *_ = np.linalg.lstsq(X, d["cv" + k], rcond=None)
        d["cvr" + k] = d["cv" + k] - X @ coef
    groups = pd.Series(range(len(d))).groupby(d.PLAYER_ID.astype(str).to_numpy()).indices
    ids = list(groups)

    def corr_ci(a, b, n=1000):
        out = []
        for _ in range(n):
            idx = np.concatenate([groups[ids[i]] for i in RNG.choice(len(ids), len(ids))])
            out.append(np.corrcoef(d[a].values[idx], d[b].values[idx])[0, 1])
        return {"r": float(np.corrcoef(d[a], d[b])[0, 1]), "ci95": [float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))]}

    res = {"n_player_pairs": len(d), "median_cv": float(np.median(np.r_[d.cv1, d.cv2])),
           "cv_iqr": [float(np.percentile(d.cv1, 25)), float(np.percentile(d.cv1, 75))],
           "yoy_corr_cv": corr_ci("cv1", "cv2"),
           "yoy_corr_cv_given_mean": corr_ci("cvr1", "cvr2"),
           "yoy_corr_fpts_mean_reference": corr_ci("fp1", "fp2"),
           "by_pair_cv_given_mean": {p: float(np.corrcoef(g.cvr1, g.cvr2)[0, 1]) for p, g in d.groupby("pair")}}
    # Shrinkage-style: how much of a player's CV deviation carries over?
    res["slope_cv_given_mean_next_on_prev"] = float(np.polyfit(d.cvr1, d.cvr2, 1)[0])
    return res


def pool(pg_s, healthy):
    st = player_season_stats(pg_s)
    pids = st[(st.mpg >= 20) & (st.gp >= 20)].index
    weeks = full_weeks(pg_s)
    W = weekly_matrix(pg_s, pids, weeks)
    if healthy:
        played = W.notna().mean(axis=1)
        W = W[played >= 0.9]
        W = W.apply(lambda r: r.fillna(r.mean()), axis=1)
    else:
        W = W.fillna(0.0)
    return W


def sim_stats(P, n_teams, rng, size=10):
    """P: players x weeks. Returns stats for equal-mean pairs and favorite/underdog pairs."""
    n = P.shape[0]
    idx = np.argsort(rng.random((n_teams, n)), axis=1)[:, :size]
    T = P[idx].sum(axis=1)                               # teams x weeks
    m, s = T.mean(1), T.std(1)
    out = {}
    # Equal means: pair neighbours in sorted order.
    order = np.argsort(m)
    a, b = order[0::2], order[1::2]
    k = min(len(a), len(b))
    a, b = a[:k], b[:k]
    close = np.abs(m[a] - m[b]) / m[a] < 0.005
    a, b = a[close], b[close]
    low = np.where(s[a] < s[b], a, b)
    high = np.where(s[a] < s[b], b, a)
    win = ((T[low] > T[high]).mean(1) + 0.5 * (T[low] == T[high]).mean(1))
    out["eq_pairs"] = int(len(a))
    out["eq_low_var_win"] = float(win.mean())
    big = s[high] / s[low] > 1.15
    out["eq_low_var_win_sd_ratio_gt_1.15"] = float(win[big].mean()) if big.any() else np.nan
    out["eq_sd_ratio_median"] = float(np.median(s[high] / s[low]))
    # Skewness of the low vs high variance teams (explains any deviation from 50%).
    # Favorites: random pairs, favorite 2-8% ahead on mean.
    p = rng.permutation(n_teams)
    a, b = p[0::2], p[1::2]
    fav = np.where(m[a] >= m[b], a, b)
    dog = np.where(m[a] >= m[b], b, a)
    gap = (m[fav] - m[dog]) / m[dog]
    band = (gap > 0.02) & (gap < 0.08)
    fav, dog = fav[band], dog[band]
    fw = (T[fav] > T[dog]).mean(1) + 0.5 * (T[fav] == T[dog]).mean(1)
    # Compare favorites with lower SD vs higher SD than the underdog, adjusting for gap via regression.
    x_low = (s[fav] < s[dog]).astype(float)
    X = np.column_stack([np.ones(len(fav)), gap[band], x_low])
    coef, *_ = np.linalg.lstsq(X, fw, rcond=None)
    out["fav_pairs"] = int(len(fav))
    out["fav_win"] = float(fw.mean())
    out["fav_win_lower_sd"] = float(fw[x_low == 1].mean())
    out["fav_win_higher_sd"] = float(fw[x_low == 0].mean())
    out["fav_lower_sd_effect_gap_adjusted"] = float(coef[2])
    # Same for underdogs (mirror): does the underdog with higher SD win more?
    return out


def sim_boot(P, n_teams=20000, B=200, seed=0):
    rng = np.random.default_rng(seed)
    point = sim_stats(P, n_teams, rng)
    keys = [k for k, v in point.items() if isinstance(v, float)]
    reps = {k: [] for k in keys}
    for _ in range(B):
        Pb = P[rng.choice(P.shape[0], P.shape[0])]    # resample players
        st = sim_stats(Pb, n_teams, rng)
        for k in keys:
            reps[k].append(st[k])
    return {k: {"est": point[k], "ci95": [float(np.nanpercentile(reps[k], 2.5)), float(np.nanpercentile(reps[k], 97.5))]}
            if k in keys else point[k] for k in point}


def prior_season_sim(pg, prev, cur, current_healthy=False, n_teams=20000, B=200, seed=1):
    """Realistic version: build pairs of teams equal on LAST season's weekly mean; the one with the lower
    LAST-season weekly SD sum - does it win more head-to-head weeks THIS season?"""
    # Last season's weekly mean/variance use only weeks he played: zero weeks would mix injuries into
    # "variance" and also drag the mean down (tested first: that makes high-variance teams look
    # underrated, a mean bias, not a consistency effect).
    st = player_season_stats(pg[prev])
    pids = st[(st.mpg >= 20) & (st.gp >= 20)].index
    Wp = weekly_matrix(pg[prev], pids, full_weeks(pg[prev]))
    Wc = pool(pg[cur], healthy=current_healthy)
    ids = Wp.index.intersection(Wc.index)
    Pp, Pc = Wp.loc[ids].to_numpy(), Wc.loc[ids].to_numpy()
    mu_p, var_p = np.nanmean(Pp, 1), np.nanvar(Pp, 1)

    def stat(Pc_, mu_, var_, rng):
        n = len(mu_)
        idx = np.argsort(rng.random((n_teams, n)), axis=1)[:, :10]
        m_prior, s_prior = mu_[idx].sum(1), np.sqrt(var_[idx].sum(1))
        T = Pc_[idx].sum(1)
        order = np.argsort(m_prior)
        a, b = order[0::2], order[1::2]
        k = min(len(a), len(b))
        a, b = a[:k], b[:k]
        close = np.abs(m_prior[a] - m_prior[b]) / m_prior[a] < 0.005
        a, b = a[close], b[close]
        low = np.where(s_prior[a] < s_prior[b], a, b)
        high = np.where(s_prior[a] < s_prior[b], b, a)
        w = (T[low] > T[high]).mean(1) + 0.5 * (T[low] == T[high]).mean(1)
        realized_sd_ratio = np.median(T[high].std(1) / T[low].std(1))
        gap = (T[low].mean(1) - T[high].mean(1)) / T[high].mean(1)
        # Win share at equal realized means: intercept of win share on the realized mean gap.
        coef, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(gap)), gap]), w, rcond=None)
        return float(w.mean()), float(coef[0]), float(gap.mean()), float(realized_sd_ratio), len(a)

    rng = np.random.default_rng(seed)
    est, est_adj, gap, ratio, npairs = stat(Pc, mu_p, var_p, rng)
    reps = []
    for _ in range(B):
        j = rng.choice(len(ids), len(ids))
        reps.append(stat(Pc[j], mu_p[j], var_p[j], rng)[:3])
    reps = np.array(reps)
    ci = lambda k: [float(np.percentile(reps[:, k], 2.5)), float(np.percentile(reps[:, k], 97.5))]
    return {"seasons": f"{prev} -> {cur}", "current_season_pool": "healthy_only" if current_healthy else "as_played",
            "n_players": len(ids), "pairs": npairs,
            "low_prior_var_team_win_share": {"est": est, "ci95": ci(0)},
            "low_prior_var_team_win_share_at_equal_realized_mean": {"est": est_adj, "ci95": ci(1)},
            "low_prior_var_team_realized_mean_gap_pct": {"est": 100 * gap, "ci95": [100 * x for x in ci(2)]},
            "median_realized_sd_ratio_high_over_low": ratio}


def single_player_effect(pg, season):
    """How much can one roster spot move team weekly SD? Swap the highest-CV for the lowest-CV quartile
    player at similar mean inside a typical team."""
    W = pool(pg[season], healthy=False)
    P = W.to_numpy()
    mu, sd = P.mean(1), P.std(1)
    team_sd = np.sqrt(10 * np.median(sd ** 2))
    q = pd.qcut(mu, 5, labels=False)
    diffs = [np.percentile(sd[q == k], 75) - np.percentile(sd[q == k], 25) for k in range(5)]
    return {"median_player_weekly_sd": float(np.median(sd)), "typical_team_weekly_sd": float(team_sd),
            "typical_team_weekly_mean": float(10 * np.median(mu)),
            "iqr_player_weekly_sd_within_mean_quintile": float(np.median(diffs)),
            "team_sd_change_pct_from_one_swap": float((np.sqrt(team_sd ** 2 + (np.median(sd) + np.median(diffs) / 2) ** 2
                                                              - (np.median(sd) - np.median(diffs) / 2) ** 2) / team_sd - 1) * 100)}


def test2(pg):
    res = {"stability": stability(pg)}
    print("T2a", json.dumps(res["stability"]), flush=True)
    for s in ("2024-25", "2025-26"):
        for healthy in (False, True):
            P = pool(pg[s], healthy).to_numpy()
            key = f"sim_{s}_{'healthy_only' if healthy else 'as_played_zero_if_out'}"
            res[key] = {"n_players": int(P.shape[0]), "n_weeks": int(P.shape[1]), **sim_boot(P)}
            print(key, json.dumps(res[key]), flush=True)
    res["prior_season_selection_as_played"] = prior_season_sim(pg, "2024-25", "2025-26")
    res["prior_season_selection_healthy"] = prior_season_sim(pg, "2024-25", "2025-26", current_healthy=True)
    print("prior", json.dumps(res["prior_season_selection_as_played"]), json.dumps(res["prior_season_selection_healthy"]), flush=True)
    res["one_roster_spot"] = single_player_effect(pg, "2025-26")
    return res


def main():
    pg, tg = bt.load()
    res = {"TEST1_coaching_changes": test1(pg, tg)}
    print("T1", json.dumps(res["TEST1_coaching_changes"], indent=1), flush=True)
    res["TEST2_weekly_consistency"] = test2(pg)
    print("RESULTS", json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
