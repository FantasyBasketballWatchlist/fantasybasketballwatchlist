"""Do NBA tracking / hustle stats predict future fantasy stats beyond the stats' own rates?

Run:  python -m analysis.test_tracking_hustle      (writes data/cache/tracking/test_tracking_hustle_results.json)

At every 3rd weekly checkpoint (2021-22..2025-26) we pull tracking data for games strictly
before the checkpoint (date_to = checkpoint - 1 day) and test:

  C1 deflections -> steals, contested shots -> blocks     (LeagueHustleStatsPlayer)
  C2 potential assists -> assists                          (LeagueDashPtStats, Passing)
  C3 rebound chances -> rebounds                           (LeagueDashPtStats, Rebounding)
  C4 shot-quality luck: actual eFG minus eFG expected from defender-distance mix
                                                           (LeagueDashPlayerPtShot)
  P  preseason version of C1-C3 (last season's tracking -> next season's rates)

Stat candidates: exp = OLS of the stat's to-date rate on tracking rates (per game);
new = rate + w * (exp - rate); FPTS candidate = current prediction + weight * w * (exp - rate).
A control uses minutes only in place of tracking, to separate "tracking" from plain regression
to the mean. Everything is fit leave-one-season-out; clustered bootstrap by player.
"""
import datetime as dt
import json
import os
import time
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd
from nba_api.stats.endpoints import LeagueDashPlayerPtShot, LeagueDashPtStats, LeagueHustleStatsPlayer

from analysis import backtest as bt
import nba_data

warnings.filterwarnings("ignore")
RNG = np.random.default_rng(33)
CACHE = os.path.join(nba_data.CACHE_DIR, "tracking")
OUT = os.path.join(CACHE, "test_tracking_hustle_results.json")
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
CP_EVERY = 3            # every 3rd weekly checkpoint
BUCKETS = ["0-2 Feet - Very Tight", "2-4 Feet - Tight", "4-6 Feet - Open", "6+ Feet - Wide Open"]
N_BOOT = 500


# ---------------------------------------------------------------- data
def _fetch(name, fn):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, name + ".csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    last = None
    for attempt in range(4):
        try:
            time.sleep(1.5)
            df = fn()
            df.to_csv(path, index=False)
            return df
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (attempt + 1))
    raise last


def _us(d):
    return dt.date.fromisoformat(d).strftime("%m/%d/%Y")


def tracking(kind, season, date_from=None, date_to=None):
    """Totals for games in [date_from, date_to] (whole season if both None)."""
    tag = f"{season}_{date_from}_{date_to}" if date_to else f"{season}_full"
    kw = dict(season=season, timeout=60)
    if date_to:
        kw.update(date_from_nullable=_us(date_from), date_to_nullable=_us(date_to))
    if kind == "hustle":
        fn = lambda: LeagueHustleStatsPlayer(per_mode_time="Totals", **kw).get_data_frames()[0]
    elif kind in ("Passing", "Rebounding"):
        fn = lambda: LeagueDashPtStats(pt_measure_type=kind, player_or_team="Player", per_mode_simple="Totals",
                                       **kw).get_data_frames()[0]
    else:  # defender-distance bucket index
        b = BUCKETS[int(kind[-1])]
        fn = lambda: LeagueDashPlayerPtShot(close_def_dist_range_nullable=b, per_mode_simple="Totals",
                                            **kw).get_data_frames()[0]
    name = f"tracking_{kind.lower()}_{tag}"
    return _fetch(name, fn)


def features(season, date_from, date_to):
    """Per-player tracking totals for a date range (one row per player)."""
    h = tracking("hustle", season, date_from, date_to).groupby("PLAYER_ID")[
        ["DEFLECTIONS", "CONTESTED_SHOTS_2PT", "CONTESTED_SHOTS_3PT", "LOOSE_BALLS_RECOVERED"]].sum()
    p = tracking("Passing", season, date_from, date_to).groupby("PLAYER_ID")[
        ["POTENTIAL_AST", "AST_PTS_CREATED", "SECONDARY_AST", "PASSES_MADE", "AST"]].sum().rename(columns={"AST": "AST_trk"})
    r = tracking("Rebounding", season, date_from, date_to).groupby("PLAYER_ID")[
        ["OREB_CHANCES", "DREB_CHANCES", "REB_CHANCES", "REB_CONTEST", "REB"]].sum().rename(columns={"REB": "REB_trk"})
    return h.join(p, how="outer").join(r, how="outer")


def shot_luck(season, date_from, date_to):
    """Per player: actual eFG, eFG expected from his shot mix by defender distance, FGA covered."""
    frames = []
    for i in range(4):
        d = tracking(f"shot{i}", season, date_from, date_to)
        d = d.groupby("PLAYER_ID")[["FG2A", "FG2M", "FG3A", "FG3M"]].sum()
        p2 = d.FG2M.sum() / d.FG2A.sum()
        p3 = d.FG3M.sum() / d.FG3A.sum()
        d["exp_pts"] = d.FG2A * p2 + 1.5 * d.FG3A * p3        # expected eFG-made
        d["act_pts"] = d.FG2M + 1.5 * d.FG3M
        d["fga"] = d.FG2A + d.FG3A
        frames.append(d[["exp_pts", "act_pts", "fga"]])
    t = pd.concat(frames).groupby(level=0).sum()
    lg = t.act_pts.sum() / t.fga.sum()
    t = t[t.fga > 0]
    return pd.DataFrame({"efg": t.act_pts / t.fga, "xefg": t.exp_pts / t.fga, "trk_fga": t.fga, "lg_efg": lg})


# ---------------------------------------------------------------- rows
STATS = ["STL", "BLK", "AST", "REB", "FGA", "FGM", "FG3M", "OREB", "DREB"]


def checkpoint_rows(season, pg):
    cps = bt.checkpoints(pg, 28)[::CP_EVERY]
    first = min(pg.GAME_DATE)
    out = []
    for c in cps:
        dto = (dt.date.fromisoformat(c) - dt.timedelta(days=1)).isoformat()
        f = features(season, first, dto)
        sl = shot_luck(season, first, dto)
        for pid, g in pg.groupby("PLAYER_ID"):
            dates = g.GAME_DATE.tolist()
            i = bisect_left(dates, c)
            if i < 10 or len(dates) - i < 10:
                continue
            fp, mins = g.FPTS.to_numpy(float), g.MIN.to_numpy(float)
            mS = mins[:i].mean()
            if mS < 12:
                continue
            S, L5, m5 = fp[:i].mean(), fp[i - 5:i].mean(), mins[i - 5:i].mean()
            dm = (S / mS) * (m5 - mS)
            pred = S + 0.3 * dm + 0.1 * (L5 - S - dm)
            row = {"season": season, "checkpoint": c, "PLAYER_ID": pid, "n": i, "mpg": mS, "S": S,
                   "pred": 2.964 + 0.910 * pred, "A": fp[i:].mean()}
            for s in STATS:
                v = g[s].to_numpy(float)
                row[f"{s}_S"], row[f"{s}_A"] = v[:i].mean(), v[i:].mean()
            if pid in f.index:
                for k, v in f.loc[pid].items():
                    row[f"{k}_pg"] = v / i
            if pid in sl.index:
                row.update(sl.loc[pid].to_dict())
            out.append(row)
        print(season, c, len(out), flush=True)
    return pd.DataFrame(out)


# ---------------------------------------------------------------- evaluation
def boot(d, e_new, e_old, n=N_BOOT):
    e = np.asarray(e_new) - np.asarray(e_old)
    groups = pd.Series(range(len(d))).groupby(d.PLAYER_ID.astype(str).to_numpy()).indices
    ids = list(groups)
    reps = [e[np.concatenate([groups[ids[j]] for j in RNG.choice(len(ids), len(ids))])].mean() for _ in range(n)]
    return {"diff": float(e.mean()), "ci95": [float(np.percentile(reps, 2.5)), float(np.percentile(reps, 97.5))]}


def judge(b, per_season):
    lo, hi = b["ci95"]
    wins = sum(v < 0 for v in per_season.values())
    if hi < 0 and wins > len(per_season) / 2:
        return "better"
    if lo > 0 and len(per_season) - wins > len(per_season) / 2:
        return "worse"
    return "tie"


def ols(X, y):
    X = np.column_stack([np.ones(len(X)), X])
    c, *_ = np.linalg.lstsq(X, y, rcond=None)
    return c


def stat_candidate(d, stat, xcols, mult, rate_col=None, target_col=None, fpts_pred="pred", fpts_actual="A",
                   return_frame=False):
    """Leave-one-season-out: exp = a + b.X (fit on to-date rates), new = rate + w (exp - rate)."""
    rate_col = rate_col or f"{stat}_S"
    target_col = target_col or f"{stat}_A"
    d = d.dropna(subset=xcols + [rate_col, target_col]).reset_index(drop=True)
    d["adj"], d["stat_new"] = np.nan, np.nan
    fits = {}
    for s in sorted(d.season.unique()):
        tr, te = d.season != s, d.season == s
        c = ols(d.loc[tr, xcols].to_numpy(float), d.loc[tr, rate_col].to_numpy(float))
        gap = lambda m: c[0] + d.loc[m, xcols].to_numpy(float) @ c[1:] - d.loc[m, rate_col].to_numpy(float)
        g_tr = gap(tr)
        y = (d.loc[tr, target_col] - d.loc[tr, rate_col]).to_numpy(float)
        w = float((g_tr * y).sum() / (g_tr ** 2).sum())
        d.loc[te, "stat_new"] = d.loc[te, rate_col] + w * gap(te)
        d.loc[te, "adj"] = mult * w * gap(te)
        fits[s] = {"exp_coef": [float(x) for x in c], "w": w}
    d["new"] = d[fpts_pred] + d.adj
    e_new, e_old = np.abs(d.new - d[fpts_actual]), np.abs(d[fpts_pred] - d[fpts_actual])
    per = {s: float((e_new - e_old)[d.season == s].mean()) for s in sorted(d.season.unique())}
    b = boot(d, e_new, e_old)
    st_new, st_old = np.abs(d.stat_new - d[target_col]), np.abs(d[rate_col] - d[target_col])
    out = {"n": len(d), "n_players": int(d.PLAYER_ID.nunique()), "features": xcols, "fits": fits,
            "fpts_mae_current": float(e_old.mean()), "fpts_mae_new": float(e_new.mean()),
            "fpts_new_minus_current": b, "fpts_per_season": per,
            "stat_mae_rate": float(st_old.mean()), "stat_mae_new": float(st_new.mean()),
            "stat_new_minus_rate": boot(d, st_new, st_old),
            "stat_per_season": {s: float((st_new - st_old)[d.season == s].mean()) for s in sorted(d.season.unique())},
            "verdict": judge(b, per)}
    return (out, d) if return_frame else out


def luck_candidate(d, feat_fn, label):
    d = d.dropna(subset=["efg", "xefg"]).reset_index(drop=True)
    d["x"] = feat_fn(d)
    d["new"] = np.nan
    fits = {}
    for s in sorted(d.season.unique()):
        tr, te = d.season != s, d.season == s
        r = (d.loc[tr, "A"] - d.loc[tr, "pred"]).to_numpy(float)
        x = d.loc[tr, "x"].to_numpy(float)
        b = float((x * r).sum() / (x * x).sum())
        d.loc[te, "new"] = d.loc[te, "pred"] + b * d.loc[te, "x"]
        fits[s] = b
    e_new, e_old = np.abs(d.new - d.A), np.abs(d.pred - d.A)
    per = {s: float((e_new - e_old)[d.season == s].mean()) for s in sorted(d.season.unique())}
    b = boot(d, e_new, e_old)
    # Does luck predict the future change in eFG itself?
    fut_efg = (d.FGM_A + 0.5 * d.FG3M_A) / d.FGA_A
    now_efg = (d.FGM_S + 0.5 * d.FG3M_S) / d.FGA_S
    corr = float(np.corrcoef((d.efg - d.xefg), fut_efg - now_efg)[0, 1])
    return {"label": label, "n": len(d), "coef_by_heldout_season": fits, "fpts_mae_current": float(e_old.mean()),
            "fpts_mae_new": float(e_new.mean()), "fpts_new_minus_current": b, "fpts_per_season": per,
            "corr_luck_with_future_efg_change": corr, "verdict": judge(b, per)}


# ---------------------------------------------------------------- preseason
def preseason_rows(pg):
    rows = []
    for tgt in SEASONS:
        prev = nba_data.previous_season(tgt)
        f = features(prev, None, None)
        a = pg[prev].groupby("PLAYER_ID")
        b = pg[tgt].groupby("PLAYER_ID")
        A = a[STATS + ["FPTS", "MIN"]].mean().join(a.size().rename("gp"))
        B = b[STATS + ["FPTS"]].mean().join(b.size().rename("gp"))
        ids = A[A.gp >= 20].index.intersection(B[B.gp >= 20].index)
        for pid in ids:
            r = {"season": tgt, "PLAYER_ID": pid, "pred": A.FPTS[pid], "A": B.FPTS[pid], "mpg": A.MIN[pid]}
            for s in STATS:
                r[f"{s}_S"], r[f"{s}_A"] = A.loc[pid, s], B.loc[pid, s]
            if pid in f.index:
                for k, v in f.loc[pid].items():
                    r[f"{k}_pg"] = v / A.gp[pid]
            rows.append(r)
    return pd.DataFrame(rows)


SPECS = {
    "C1_steals_deflections": ("STL", ["DEFLECTIONS_pg"], 4),
    "C1_steals_deflections_plus_minutes": ("STL", ["DEFLECTIONS_pg", "mpg"], 4),
    "C1_steals_control_minutes_only": ("STL", ["mpg"], 4),
    "C1_blocks_contests": ("BLK", ["CONTESTED_SHOTS_2PT_pg", "CONTESTED_SHOTS_3PT_pg"], 4),
    "C1_blocks_control_minutes_only": ("BLK", ["mpg"], 4),
    "C2_assists_potential": ("AST", ["POTENTIAL_AST_pg"], 2),
    "C2_assists_potential_plus_passes": ("AST", ["POTENTIAL_AST_pg", "PASSES_MADE_pg", "SECONDARY_AST_pg"], 2),
    "C2_assists_control_minutes_only": ("AST", ["mpg"], 2),
    "C3_rebounds_chances": ("REB", ["OREB_CHANCES_pg", "DREB_CHANCES_pg"], 1),
    "C3_rebounds_control_minutes_only": ("REB", ["mpg"], 1),
}


def sanity(d):
    """Tracking AST/REB per game should match box-score AST/REB per game to date."""
    x = d.dropna(subset=["AST_trk_pg", "REB_trk_pg"])
    return {"ratio_tracking_to_box_AST": float(x.AST_trk_pg.sum() / x.AST_S.sum()),
            "ratio_tracking_to_box_REB": float(x.REB_trk_pg.sum() / x.REB_S.sum()),
            "share_rows_with_hustle": float(d.DEFLECTIONS_pg.notna().mean()),
            "share_rows_with_shot_luck": float(d.efg.notna().mean()),
            "mean_deflections_pg": float(d.DEFLECTIONS_pg.mean()), "mean_potential_ast_pg": float(d.POTENTIAL_AST_pg.mean()),
            "mean_reb_chances_pg": float(d.REB_CHANCES_pg.mean()),
            "corr_to_date_STL_DEFL": float(d[["STL_S", "DEFLECTIONS_pg"]].corr().iloc[0, 1]),
            "corr_to_date_AST_POTAST": float(d[["AST_S", "POTENTIAL_AST_pg"]].corr().iloc[0, 1])}


def main():
    pg, _ = bt.load()
    frames = []
    for s in SEASONS:
        frames.append(checkpoint_rows(s, pg[s]))
    d = pd.concat(frames, ignore_index=True)
    res = {"n_rows": len(d), "n_player_seasons": int(d.groupby(["season", "PLAYER_ID"]).ngroups),
           "checkpoints": {s: sorted(g.checkpoint.unique().tolist()) for s, g in d.groupby("season")},
           "sanity": sanity(d), "in_season": {}, "preseason": {}}
    print(json.dumps(res["sanity"]), flush=True)
    for name, (stat, x, m) in SPECS.items():
        res["in_season"][name] = stat_candidate(d, stat, x, m)
        r = res["in_season"][name]
        print(name, r["fpts_new_minus_current"], r["stat_new_minus_rate"]["diff"], r["verdict"], flush=True)

    # Combined: all four tracking adjustments at once (each fit leave-one-season-out on the common rows).
    names = ["C1_steals_deflections", "C1_blocks_contests", "C2_assists_potential", "C3_rebounds_chances"]
    dd = d.dropna(subset=sum([SPECS[n][1] for n in names], [])).reset_index(drop=True)
    total = np.zeros(len(dd))
    for n in names:
        _, fr = stat_candidate(dd, *SPECS[n], return_frame=True)
        total += fr.adj.to_numpy(float)
    e_new, e_old = np.abs(dd.pred + total - dd.A), np.abs(dd.pred - dd.A)
    per = {s: float((e_new - e_old)[dd.season == s].mean()) for s in sorted(dd.season.unique())}
    b = boot(dd, e_new, e_old)
    res["in_season"]["combined_C1_C2_C3"] = {"n": len(dd), "fpts_new_minus_current": b, "fpts_per_season": per,
                                             "verdict": judge(b, per)}
    print("combined", b, per, flush=True)

    res["in_season"]["C4_luck_defender_distance"] = luck_candidate(d, lambda x: (x.efg - x.xefg) * x.FGA_S, "luck x FGA/g")
    res["in_season"]["C4_control_raw_efg_vs_league"] = luck_candidate(d, lambda x: (x.efg - x.lg_efg) * x.FGA_S,
                                                                     "(eFG - league eFG) x FGA/g")
    for k in ["C4_luck_defender_distance", "C4_control_raw_efg_vs_league"]:
        print(k, res["in_season"][k]["fpts_new_minus_current"], res["in_season"][k]["fpts_per_season"], flush=True)

    p = preseason_rows(pg)
    res["preseason"]["n_rows"] = len(p)
    for name, (stat, x, m) in SPECS.items():
        res["preseason"][name] = stat_candidate(p, stat, x, m)
        r = res["preseason"][name]
        print("pre", name, r["fpts_new_minus_current"], r["stat_new_minus_rate"], r["verdict"], flush=True)

    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
