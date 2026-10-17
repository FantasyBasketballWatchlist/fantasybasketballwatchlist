"""Three candidate BPV improvements, tested out of sample.

Run:  python -m analysis.test_schedule_positions_uncertainty   (prints JSON results)

TEST 1  Fantasy-playoff schedule: do teams' game counts in the fantasy playoffs
        (ESPN weeks 21-24) differ enough to matter for predicting playoff FPTS?
        Also fetches the 2026-27 schedule and writes data/cache/playoff_games_2026-27.csv.
TEST 2  Positional replacement levels (ESPN lineup PG,SG,SF,PF,C,G,F,3xUTIL; 10 teams,
        13-man rosters) vs the single 130th-best replacement, plus a lineup-constrained
        snake-draft simulation (positional VOR vs overall value).
TEST 3  Uncertainty bands: fit 10th/90th percentile error bands for the in-season
        production estimate on TRAIN seasons, check 80% coverage on the TEST season.

Definitions
  Fantasy playoff window: the 4 Monday-Sunday weeks ending on the Sunday that ends the
  week containing the last regular-season day (every season here ends on a Sunday, so
  it is exactly the last 28 days of the regular season).
  Positions: nba_api PlayerIndex (historical, one call) gives G / F / C / G-F / F-C...
  G -> PG, SG, G; F -> SF, PF, F; C -> C; hyphenated -> union; everyone -> UTIL.
"""
import datetime as dt
import json
import os
import time
import warnings

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment

from analysis import backtest as bt
import ratings

warnings.filterwarnings("ignore")
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cache")
RNG = np.random.default_rng(2027)
B = 300


def ci(v):
    lo, hi = np.percentile(v, [2.5, 97.5])
    return [round(float(lo), 3), round(float(hi), 3)]


def cluster_boot(df, stat, n=B, key="PLAYER_ID"):
    groups = list(df.groupby(key).indices.values())
    out = []
    for _ in range(n):
        pick = RNG.integers(0, len(groups), len(groups))
        out.append(stat(df.iloc[np.concatenate([groups[i] for i in pick])]))
    return out


# ============================================================== TEST 1
def playoff_window(last_day):
    last = dt.date.fromisoformat(last_day)
    end = last + dt.timedelta(days=(6 - last.weekday()))       # Sunday of the final week
    start = end - dt.timedelta(days=27)                          # Monday, 4 weeks earlier
    return start.isoformat(), end.isoformat()


def test1(pg, tg):
    res = {"window_definition": "4 Mon-Sun weeks ending the Sunday of the week containing the last regular-season day"}
    rows = []
    for s in ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]:
        t, p = tg[s], pg[s]
        start, end = playoff_window(t.GAME_DATE.max())
        cutoff = (dt.date.fromisoformat(start) - dt.timedelta(days=28)).isoformat()
        inwin = t[(t.GAME_DATE >= start) & (t.GAME_DATE <= end)]
        counts = inwin.groupby("TEAM_ID").size().reindex(t.TEAM_ID.unique(), fill_value=0)
        league_avg = counts.mean()
        res[s] = {"window": [start, end], "base_cutoff": cutoff, "min": int(counts.min()), "max": int(counts.max()),
                  "sd": round(float(counts.std(ddof=0)), 3), "mean": round(float(league_avg), 3),
                  "distribution": {int(k): int(v) for k, v in counts.value_counts().sort_index().items()}}
        sched = {k: sorted(v) for k, v in t.groupby("TEAM_ID").GAME_DATE}
        before = p[p.GAME_DATE < cutoff]
        win = p[(p.GAME_DATE >= start) & (p.GAME_DATE <= end)].groupby("PLAYER_ID").FPTS.sum()
        for pid, g in before.sort_values("GAME_DATE").groupby("PLAYER_ID"):
            if len(g) < 10 or g.MIN.mean() < 20:
                continue
            team = g.TEAM_ID.iloc[-1]
            team_before = sum(1 for d in sched[team] if d < cutoff)
            avail = min(1.0, len(g) / max(team_before, 1))
            rows.append({"season": s, "PLAYER_ID": pid, "base": g.FPTS.mean(), "avail": avail,
                         "team_games": counts[team], "league_avg": league_avg, "actual": win.get(pid, 0.0)})
    d = pd.DataFrame(rows)
    out = {}
    for label, a in [("availability_to_date", d.avail), ("assume_plays_every_game", 1.0)]:
        e_team = (d.base * a * d.team_games - d.actual).abs()
        e_avg = (d.base * a * d.league_avg - d.actual).abs()
        dd = d.assign(e_team=e_team, e_avg=e_avg)
        diff = lambda x: x.e_team.mean() - x.e_avg.mean()
        out[label] = {"mae_team_counts": round(float(e_team.mean()), 2), "mae_league_avg": round(float(e_avg.mean()), 2),
                      "diff_team_minus_avg": round(float(diff(dd)), 3), "diff_ci95": ci(cluster_boot(dd, diff)),
                      "by_season_diff": {s: round(float(diff(g)), 3) for s, g in dd.groupby("season")}}
    out["n_player_seasons"], out["n_players"] = len(d), int(d.PLAYER_ID.nunique())
    out["mean_actual_window_fpts"] = round(float(d.actual.mean()), 1)
    out["share_zero_window_fpts"] = round(float((d.actual == 0).mean()), 3)
    # Among players who actually played in the window: does per-team-game scaling help there?
    played = d[d.actual != 0].copy()
    played["e_team"] = (played.base * played.avail * played.team_games - played.actual).abs()
    played["e_avg"] = (played.base * played.avail * played.league_avg - played.actual).abs()
    diff = lambda x: x.e_team.mean() - x.e_avg.mean()
    out["played_in_window_only"] = {"n": len(played), "mae_team_counts": round(float(played.e_team.mean()), 2),
                                    "mae_league_avg": round(float(played.e_avg.mean()), 2),
                                    "diff": round(float(diff(played)), 3), "diff_ci95": ci(cluster_boot(played, diff))}
    res["prediction"] = out
    res["schedule_2026_27"] = schedule_2026_27()
    return res


def schedule_2026_27():
    raw_path = os.path.join(CACHE, "schedule_2026-27.csv")
    if not os.path.exists(raw_path):
        from nba_api.stats.endpoints import ScheduleLeagueV2
        time.sleep(1)
        s = ScheduleLeagueV2(season="2026-27", league_id="00", timeout=60).get_data_frames()[0]
        s = s[s.gameId.astype(str).str[:3] == "002"]
        s = s[["gameId", "gameDateEst", "gameLabel", "gameSubtype", "homeTeam_teamTricode", "awayTeam_teamTricode"]]
        s.to_csv(raw_path, index=False)
    s = pd.read_csv(raw_path, dtype={"gameId": str})
    s["date"] = s.gameDateEst.str[:10]
    tbd = s[s.homeTeam_teamTricode.isna()]
    s = s[s.homeTeam_teamTricode.notna()]
    long = pd.concat([s[["date", "homeTeam_teamTricode"]].rename(columns={"homeTeam_teamTricode": "T"}),
                      s[["date", "awayTeam_teamTricode"]].rename(columns={"awayTeam_teamTricode": "T"})])
    start, end = playoff_window(long.date.max())
    total = long.groupby("T").size()
    po = long[(long.date >= start) & (long.date <= end)].groupby("T").size().reindex(total.index, fill_value=0)
    out = pd.DataFrame({"TEAM_ABBREVIATION": total.index, "playoff_games": po.values, "total_games": total.values})
    out.sort_values(["playoff_games", "TEAM_ABBREVIATION"], ascending=[False, True]).to_csv(
        os.path.join(CACHE, "playoff_games_2026-27.csv"), index=False)
    return {"available": True, "regular_season_games_listed": int(len(s) + len(tbd)),
            "tbd_placeholder_games": int(len(tbd)), "tbd_dates": sorted(tbd.date.unique().tolist()),
            "first_day": long.date.min(), "last_day": long.date.max(), "window": [start, end],
            "teams": int(len(total)), "games_per_team_min_max": [int(total.min()), int(total.max())],
            "playoff_games_min_max_sd": [int(po.min()), int(po.max()), round(float(po.std(ddof=0)), 3)],
            "playoff_games_distribution": {int(k): int(v) for k, v in po.value_counts().sort_index().items()},
            "teams_by_playoff_games": {int(k): sorted(po[po == k].index.tolist()) for k in sorted(po.unique())}}


# ============================================================== TEST 2
SLOTS = ["PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "UTIL", "UTIL"]
ELIG = {"G": {"PG", "SG", "G"}, "F": {"SF", "PF", "F"}, "C": {"C"}}
POS_GROUPS = ["G", "F", "C"]


def positions():
    path = os.path.join(CACHE, "player_positions.csv")
    if not os.path.exists(path):
        from nba_api.stats.endpoints import PlayerIndex
        time.sleep(1)
        p = PlayerIndex(season="2025-26", historical_nullable="1", league_id="00", timeout=60).get_data_frames()[0]
        p = p[["PERSON_ID", "PLAYER_FIRST_NAME", "PLAYER_LAST_NAME", "POSITION", "FROM_YEAR", "TO_YEAR"]]
        p.to_csv(path, index=False)
    p = pd.read_csv(path)
    return p.set_index("PERSON_ID").POSITION


def groups_of(pos):
    if not isinstance(pos, str) or not pos:
        return {"G", "F", "C"} & set()  # unknown -> UTIL only
    return {x for x in pos.split("-") if x in ELIG}


def slot_elig(groups):
    s = {"UTIL"}
    for g in groups:
        s |= ELIG[g]
    return s


def positional_replacement(values, groups, teams=10, roster=13):
    """Greedy league-wide allocation. values: Series pid->FPTS/g; groups: pid->set of G/F/C."""
    order = values.sort_values(ascending=False).index.tolist()
    open_slots = {s: teams * SLOTS.count(s) for s in set(SLOTS)}
    pref = ["C", "PG", "SG", "SF", "PF", "G", "F", "UTIL"]
    starters, total = [], len(SLOTS) * teams
    for pid in order:
        if len(starters) == total:
            break
        el = slot_elig(groups[pid])
        for s in pref:
            if s in el and open_slots[s] > 0:
                open_slots[s] -= 1
                starters.append(pid)
                break
    st = set(starters)
    rest = [p for p in order if p not in st]
    bench = rest[: teams * (roster - len(SLOTS))]
    left_after_starters, left = rest, rest[len(bench):]
    out = {"overall_130th": float(values.sort_values(ascending=False).iloc[teams * roster - 1])}
    for g in POS_GROUPS:
        out[f"repl_{g}"] = float(next(values[p] for p in left if g in groups[p]))
        out[f"repl_{g}_starters_only"] = float(next(values[p] for p in left_after_starters if g in groups[p]))
        out[f"worst_starter_{g}"] = float(min(values[p] for p in starters if g in groups[p]))
    out["n_pool"] = len(values)
    return out


def lineup_score(roster, totals, elig):
    m = np.full((len(roster), len(SLOTS)), -1e9)
    for i, p in enumerate(roster):
        for j, s in enumerate(SLOTS):
            if s in elig[p]:
                m[i, j] = totals[p]
    r, c = linear_sum_assignment(-m)
    v = m[r, c]
    return float(v[v > -1e8].sum())


def draft(rankings, strategies, n_sims, totals, elig, rng, teams=10, rounds=13):
    seats = [s for s in strategies for _ in range(teams // len(strategies))]
    res = {s: [] for s in strategies}
    for _ in range(n_sims):
        order = seats[:]
        rng.shuffle(order)
        taken, rosters = set(), [[] for _ in range(teams)]
        ptr = {s: 0 for s in strategies}
        for rnd in range(rounds):
            for seat in (range(teams) if rnd % 2 == 0 else range(teams - 1, -1, -1)):
                rk = rankings[order[seat]]
                i = ptr[order[seat]]
                while rk[i] in taken:
                    i += 1
                ptr[order[seat]] = i
                taken.add(rk[i])
                rosters[seat].append(rk[i])
        for seat in range(teams):
            res[order[seat]].append(lineup_score(rosters[seat], totals, elig))
    return {s: float(np.mean(v)) for s, v in res.items()}


def season_pool(pg, prev, target, pos):
    a = pg[prev].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), gp=("FPTS", "size"))
    a = a[a.gp >= 20]
    tot = pg[target].groupby("PLAYER_ID").FPTS.sum()
    df = pd.DataFrame({"pred": a.fp, "actual_total": tot.reindex(a.index).fillna(0.0)})
    df["groups"] = [groups_of(pos.get(i)) for i in df.index]
    return df


def strategy_rankings(df):
    groups = df.groups.to_dict()
    rp = positional_replacement(df.pred, groups)
    R = rp["overall_130th"]
    rpos = {g: rp[f"repl_{g}"] for g in POS_GROUPS}
    pos_vor = pd.Series({p: df.pred[p] - (min(rpos[g] for g in groups[p]) if groups[p] else R) for p in df.index})
    return {"overall value (BPV-style)": df.pred.sort_values(ascending=False).index.tolist(),
            "positional VOR": pos_vor.sort_values(ascending=False).index.tolist()}, rp


def test2(pg):
    pos = positions()
    res = {"position_source": "nba_api PlayerIndex historical (G/F/C only; PG vs SG and SF vs PF not distinguishable)"}
    # 2025-26 replacement levels (realized per-game FPTS, >=20 games).
    a = pg["2025-26"].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), gp=("FPTS", "size"))
    a = a[a.gp >= 20]
    groups = {p: groups_of(pos.get(p)) for p in a.index}
    res["coverage_2025_26"] = {"players": len(a), "missing_position": int(sum(1 for g in groups.values() if not g)),
                               "counts": {g: int(sum(1 for x in groups.values() if g in x)) for g in POS_GROUPS}}
    rp = positional_replacement(a.fp, groups)
    res["replacement_2025_26"] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in rp.items()}

    strategies = ["overall value (BPV-style)", "positional VOR"]
    sims, per_boot = 1000, 20
    res["draft"] = {}
    boot_diffs = np.zeros((B, 4))
    for k, target in enumerate(["2022-23", "2023-24", "2024-25", "2025-26"]):
        prev = bt.SEASONS[bt.SEASONS.index(target) - 1]
        df = season_pool(pg, prev, target, pos)
        ranks, rp = strategy_rankings(df)
        elig = {p: slot_elig(df.groups[p]) for p in df.index}
        pt = draft(ranks, strategies, sims, df.actual_total.to_dict(), elig, np.random.default_rng(k))
        # Player bootstrap: resample the pool (duplicates become distinct players), redo everything.
        ids = df.index.to_numpy()
        for b in range(B):
            pick = RNG.integers(0, len(ids), len(ids))
            bd = df.iloc[pick].copy()
            bd.index = [f"{ids[i]}_{j}" for j, i in enumerate(pick)]
            br, _ = strategy_rankings(bd)
            be = {p: slot_elig(bd.groups[p]) for p in bd.index}
            r = draft(br, strategies, per_boot, bd.actual_total.to_dict(), be, np.random.default_rng(1000 + b))
            boot_diffs[b, k] = r[strategies[1]] - r[strategies[0]]
        # How different are the rankings? Position mix of each strategy's top 50.
        mix = {s: {g: int(sum(1 for p in ranks[s][:50] if g in df.groups[p])) for g in POS_GROUPS} for s in strategies}
        res["draft"][target] = {"pool": len(df), "preseason_replacement": {k2: round(v, 2) if isinstance(v, float) else v
                                                                             for k2, v in rp.items()},
                                "mean_team_lineup_fpts": {s: round(v, 1) for s, v in pt.items()},
                                "diff_posVOR_minus_overall": round(pt[strategies[1]] - pt[strategies[0]], 1),
                                "diff_ci95_player_bootstrap": ci(boot_diffs[:, k]),
                                "top50_position_mix": mix}
    pooled = {t: res["draft"][t]["diff_posVOR_minus_overall"] for t in res["draft"]}
    res["draft_pooled"] = {"mean_diff": round(float(np.mean(list(pooled.values()))), 1),
                           "ci95": ci(boot_diffs.mean(axis=1)),
                           "mean_team_score": round(float(np.mean([v["mean_team_lineup_fpts"][strategies[0]]
                                                                   for v in res["draft"].values()])), 0)}
    return res


# ============================================================== TEST 3
def test3(pg, tg):
    cp = pd.concat([bt.checkpoint_rows(s, pg[s], tg[s]) for s in bt.TRAIN + bt.TEST], ignore_index=True)
    cp = cp[cp.mpg_S >= 12].dropna(subset=["A_ros"]).copy()
    fpm = cp.S / cp.mpg_S.clip(lower=1)
    d_min = fpm * (cp.mpg_L5 - cp.mpg_S)
    cp["pred"] = cp.S + ratings.MINUTES_CHANGE_WEIGHT * d_min + ratings.EFFICIENCY_CHANGE_WEIGHT * (cp.L5 - cp.S - d_min)
    cp["resid"] = cp.A_ros - cp.pred
    # Team games remaining at the checkpoint (known from the schedule) for the scaled model.
    rem = []
    for s, g in cp.groupby("season"):
        t = tg[s]
        n_team = t.groupby("TEAM_ID").size().median()
        played_by = {c: t[t.GAME_DATE < c].groupby("TEAM_ID").size().median() for c in g.checkpoint.unique()}
        rem.append(pd.Series(n_team - g.checkpoint.map(played_by), index=g.index))
    cp["rem"] = pd.concat(rem).clip(lower=5)
    cp["scale"] = np.sqrt(cp.pred.clip(lower=5)) * np.sqrt(1 / cp.n_before + 1 / cp.rem)
    cp["z"] = cp.resid / cp.scale
    bins = [10, 20, 30, 45, 200]
    labels = ["10-19", "20-29", "30-44", "45+"]
    cp["bucket"] = pd.cut(cp.n_before, bins, right=False, labels=labels)
    tr, te = cp[cp.season.isin(bt.TRAIN)], cp[cp.season.isin(bt.TEST)].copy()

    q_b = tr.groupby("bucket").resid.quantile([0.1, 0.9]).unstack()
    zq = tr.z.quantile([0.1, 0.9]).to_numpy()
    q_all = tr.resid.quantile([0.1, 0.9]).to_numpy()
    te["lo_b"], te["hi_b"] = te.bucket.map(q_b[0.1]).astype(float), te.bucket.map(q_b[0.9]).astype(float)
    te["lo_s"], te["hi_s"] = zq[0] * te.scale, zq[1] * te.scale
    te["in_b"] = (te.resid >= te.lo_b) & (te.resid <= te.hi_b)
    te["in_s"] = (te.resid >= te.lo_s) & (te.resid <= te.hi_s)
    te["in_c"] = (te.resid >= q_all[0]) & (te.resid <= q_all[1])
    res = {"n_train_rows": len(tr), "n_train_players": int(tr.PLAYER_ID.nunique()),
           "n_test_rows": len(te), "n_test_players": int(te.PLAYER_ID.nunique()),
           "train_mean_resid": round(float(tr.resid.mean()), 3), "test_mean_resid": round(float(te.resid.mean()), 3),
           "train_band_by_bucket": {b: [round(float(q_b.loc[b, 0.1]), 2), round(float(q_b.loc[b, 0.9]), 2)] for b in labels},
           "train_z_quantiles": [round(float(x), 3) for x in zq]}
    for key, col, lo, hi in [("bucket_quantiles", "in_b", "lo_b", "hi_b"), ("scaled_sqrt", "in_s", "lo_s", "hi_s"),
                             ("constant_band", "in_c", None, None)]:
        width = (te[hi] - te[lo]) if lo else pd.Series(q_all[1] - q_all[0], index=te.index)
        res[key] = {"coverage": round(float(te[col].mean()), 3), "coverage_ci95": ci(cluster_boot(te, lambda x: x[col].mean())),
                    "below_share": round(float((te.resid < (te[lo] if lo else q_all[0])).mean()), 3),
                    "above_share": round(float((te.resid > (te[hi] if hi else q_all[1])).mean()), 3),
                    "median_width": round(float(width.median()), 2),
                    "by_bucket": {b: {"n": int(len(g)), "coverage": round(float(g[col].mean()), 3),
                                      "median_width": round(float(width[g.index].median()), 2)}
                                  for b, g in te.groupby("bucket")}}
    # Relative width vs level: median half-width as % of prediction.
    res["scaled_sqrt"]["median_width_pct_of_pred"] = round(float(((te.hi_s - te.lo_s) / te.pred.clip(lower=1)).median()), 3)
    # Coverage by FPTS level (does a single band per bucket fail for stars vs role players?)
    te["level"] = pd.qcut(te.pred, 3, labels=["low", "mid", "high"])
    res["coverage_by_level"] = {lvl: {"bucket_quantiles": round(float(g.in_b.mean()), 3),
                                      "scaled_sqrt": round(float(g.in_s.mean()), 3), "n": int(len(g))}
                                for lvl, g in te.groupby("level")}
    return res


def main():
    pg, tg = bt.load()
    out = {}
    out["test1"] = test1(pg, tg); print("test1 done", flush=True)
    out["test3"] = test3(pg, tg); print("test3 done", flush=True)
    out["test2"] = test2(pg); print("test2 done", flush=True)
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
