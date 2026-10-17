"""Ideas from published projection systems, each scored against current BPV out of sample.

Run:  python -m analysis.test_research_ideas     (writes analysis/test_research_ideas.json)

R1  Per-stat stabilization (Medvedovsky's padding): shrink each stat's per-minute rate toward
    last season's with its own padding (in minutes), times shrunk minutes, vs BPV's single
    FPTS-level blend with last season (8 games). Returning players, checkpoints from week 1.
R2  Lighter shrinkage for stars: blend weight k depends on last season's level.
R3  Bias check: are BPV's rest-of-season projections too extreme or too timid? Fit
    actual = a + b x projection on 2021-22..2024-25; score the recalibrated version on 2025-26.
R4  Late-season tanking/resting: do regulars on bad or clinched teams under-deliver in the
    fantasy-playoff window versus a projection made two weeks before it?
R5  Rookie draft age: does age at the start of the rookie season improve the draft-slot baseline?
R6  Usage-weighted teammate boost: when a 20+ mpg teammate is out long-term, split the gain by
    each teammate's usage (shot attempts + free throws + turnovers per minute) instead of evenly.
Tuning seasons 2021-22..2024-25, test season 2025-26 unless stated.
"""
import datetime as dt
import itertools
import json
import os
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_misc as tm
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_research_ideas.json")
COMPONENTS = {"PTS": 1, "REB": 1, "AST": 2, "STL": 4, "BLK": 4, "TOV": -2}   # plus SHOOT = 2FGM - FGA + FTM - FTA + FG3M


def add_components(g):
    g = g.copy()
    g["SHOOT"] = 2 * g.FGM - g.FGA + g.FTM - g.FTA + g.FG3M
    g["USE"] = g.FGA + 0.44 * g.FTA + g.TOV
    return g


COMP_COLS = list(COMPONENTS) + ["SHOOT"]
COMP_W = {**COMPONENTS, "SHOOT": 1}


def early_rows(pg, tg):
    """Checkpoints from week 1 for returning players (20+ games last season)."""
    rows = []
    for s in bt.TRAIN + bt.TEST:
        prev = bt.SEASONS[bt.SEASONS.index(s) - 1]
        gp = add_components(pg[prev])
        pv = gp.groupby("PLAYER_ID").agg(n=("FPTS", "size"), mins=("MIN", "sum"), fp=("FPTS", "mean"),
                                         **{c: (c, "sum") for c in COMP_COLS})
        pv = pv[pv.n >= 20]
        g_all = add_components(pg[s]).sort_values("GAME_DATE")
        for c in bt.checkpoints(g_all, 7, 7, 21):
            before, after = g_all[g_all.GAME_DATE < c], g_all[g_all.GAME_DATE >= c]
            b = before.groupby("PLAYER_ID").agg(n=("FPTS", "size"), mins=("MIN", "sum"), fp=("FPTS", "mean"),
                                                **{k: (k, "sum") for k in COMP_COLS})
            a = after.groupby("PLAYER_ID").agg(n=("FPTS", "size"), A=("FPTS", "mean"))
            ids = b.index.intersection(pv.index).intersection(a[a.n >= 10].index)
            for pid in ids:
                bb, pp_ = b.loc[pid], pv.loc[pid]
                if bb.n > 40:
                    continue
                row = {"season": s, "PLAYER_ID": pid, "n": bb.n, "mins": bb.mins, "S": bb.fp, "prev_fp": pp_.fp,
                       "prev_mpg": pp_.mins / pp_.n, "A": a.loc[pid].A}
                for k in COMP_COLS:
                    row[f"cur_{k}"] = bb[k]
                    row[f"prev_rate_{k}"] = pp_[k] / max(pp_.mins, 1)
                rows.append(row)
    return pd.DataFrame(rows)


def padded_prediction(d, pads, k_min):
    mpg = bpv.shrink(d.mins / d.n, d.n, d.prev_mpg, k_min)
    total = 0
    for k in COMP_COLS:
        rate = (d[f"cur_{k}"] + pads[k] * d[f"prev_rate_{k}"]) / (d.mins + pads[k])
        total = total + COMP_W[k] * rate
    return total * mpg


def r1_r2(pg, tg):
    d = early_rows(pg, tg)
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)
    base_tr, base_te = bpv.shrink(tr.S, tr.n, tr.prev_fp, 8), bpv.shrink(te.S, te.n, te.prev_fp, 8)
    # Coordinate descent on per-stat padding (minutes) and the minutes shrinkage k.
    grid = [0, 50, 100, 200, 400, 800, 1600, 3200]
    pads, k_min = {k: 400 for k in COMP_COLS}, 4
    for _ in range(3):
        k_min = min([0, 1, 2, 4, 8, 16], key=lambda km: bt.mae(padded_prediction(tr, pads, km), tr.A))
        for k in COMP_COLS:
            pads[k] = min(grid, key=lambda x: bt.mae(padded_prediction(tr, {**pads, k: x}, k_min), tr.A))
    new_te = padded_prediction(te, pads, k_min)
    b1 = tm.boot(te, np.abs(new_te - te.A), np.abs(base_te - te.A))
    early = te.n <= 20
    b1e = tm.boot(te[early].reset_index(drop=True), np.abs(new_te[early] - te.A[early]).to_numpy(),
                  np.abs(base_te[early] - te.A[early]).to_numpy())
    res = {"R1": {"n_train": len(tr), "n_test": len(te), "paddings_minutes": pads, "minutes_k_games": k_min,
                  "mae_current_blend": bt.mae(base_te, te.A), "mae_padded": bt.mae(new_te, te.A),
                  "padded_minus_current": b1, "verdict": tm.verdict(b1),
                  "first_20_games_only": b1e, "verdict_first_20": tm.verdict(b1e)}}
    # R2: k by last season's level.
    for d_ in (tr, te):
        d_["star"] = d_.prev_fp >= 40
    options = [(a, b) for a in (4, 6, 8, 10, 12) for b in (2, 4, 6, 8, 10, 12)]
    best = min(options, key=lambda o: bt.mae(bpv.shrink(tr.S, tr.n, tr.prev_fp, np.where(tr.star, o[1], o[0])), tr.A))
    new = bpv.shrink(te.S, te.n, te.prev_fp, np.where(te.star, best[1], best[0]))
    b2 = tm.boot(te, np.abs(new - te.A), np.abs(base_te - te.A))
    stars = te.star.to_numpy()
    b2s = tm.boot(te[stars].reset_index(drop=True), np.abs(new[stars] - te.A[stars]).to_numpy(),
                  np.abs(base_te[stars] - te.A[stars]).to_numpy())
    res["R2"] = {"best_k_regular_star": best, "stars_test": int(stars.sum()), "all": b2, "stars_only": b2s,
                 "verdict": tm.verdict(b2), "verdict_stars": tm.verdict(b2s)}
    return res


def r3(pg, tg):
    cp = pd.concat([bt.checkpoint_rows(s, pg[s], tg[s]) for s in bt.TRAIN + bt.TEST], ignore_index=True)
    cp = cp[cp.mpg_S >= 12].copy()
    per_min = cp.S / cp.mpg_S.clip(lower=1)
    dm = per_min * (cp.mpg_L5 - cp.mpg_S)
    cp["pred"] = cp.S + 0.3 * dm + 0.1 * (cp.L5 - cp.S - dm)
    tr, te = cp[cp.season.isin(bt.TRAIN)], cp[cp.season.isin(bt.TEST)].reset_index(drop=True)
    b, a = np.polyfit(tr.pred, tr.A_ros, 1)
    new = a + b * te.pred
    bb = tm.boot(te, np.abs(new - te.A_ros), np.abs(te.pred - te.A_ros))
    return {"slope": float(b), "intercept": float(a), "mean_error_train": float((tr.A_ros - tr.pred).mean()),
            "mean_error_test": float((te.A_ros - te.pred).mean()), "recalibrated_minus_current": bb, "verdict": tm.verdict(bb)}


def r4(pg, tg):
    rows = []
    for s in ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]:
        t = tg[s]
        start, _ = bpv.playoff_window(t.GAME_DATE.max())
        cut = (dt.date.fromisoformat(start) - dt.timedelta(days=14)).isoformat()
        rec = t[t.GAME_DATE < cut].groupby("TEAM_ID").WL.apply(lambda x: (x == "W").mean())
        status = pd.Series("middle", index=rec.index)
        status[rec <= 0.35] = "bad"
        status[rec >= 0.68] = "top"
        g = pg[s]
        before = g[g.GAME_DATE < cut].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"),
                                                               mpg=("MIN", "mean"), team=("TEAM_ID", "last"))
        win = g[(g.GAME_DATE >= start)].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"))
        team_games = t[t.GAME_DATE >= start].groupby("TEAM_ID").size()
        team_before = t[t.GAME_DATE < cut].groupby("TEAM_ID").size()
        ages = nba_data.player_ages(s).set_index("PLAYER_ID").AGE
        for pid, b in before[(before.mpg >= 20) & (before.n >= 30)].iterrows():
            share_before = b.n / team_before[b.team]
            w = win.loc[pid] if pid in win.index else None
            rows.append({"season": s, "PLAYER_ID": pid, "status": status[b.team], "age": ages.get(pid, np.nan),
                         "share_before": share_before,
                         "share_window": (w.n if w is not None else 0) / team_games[b.team],
                         "fp_ratio": (w.fp / b.fp) if w is not None and w.n >= 3 else np.nan,
                         "mpg_change": (w.mpg - b.mpg) if w is not None and w.n >= 3 else np.nan})
    d = pd.DataFrame(rows)
    d["games_share_drop"] = d.share_before - d.share_window
    out = {}
    for st, g in d.groupby("status"):
        out[st] = {"n": len(g), "games_share_drop": float(g.games_share_drop.mean()),
                   "fp_ratio_median": float(g.fp_ratio.median()), "mpg_change": float(g.mpg_change.mean())}
    for st in ("bad", "top"):
        sub = d[d.status.isin([st, "middle"])].reset_index(drop=True)
        x = (sub.status == st).to_numpy()
        diff = lambda z: z.games_share_drop[z.status == st].mean() - z.games_share_drop[z.status == "middle"].mean()
        boots = []
        rng = np.random.default_rng(4)
        groups = sub.groupby("PLAYER_ID").indices
        ids = list(groups)
        for _ in range(500):
            idx = np.concatenate([groups[ids[i]] for i in rng.choice(len(ids), len(ids))])
            boots.append(diff(sub.iloc[idx]))
        out[f"{st}_minus_middle_games_share_drop"] = {"diff": float(diff(sub)),
                                                      "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))]}
        old = d[(d.status == st) & (d.age >= 28)]
        out[f"{st}_veterans_28plus"] = {"n": len(old), "games_share_drop": float(old.games_share_drop.mean()),
                                        "fp_ratio_median": float(old.fp_ratio.median())}
    return out


def r5(pg):
    draft = nba_data.draft_history()
    rows = []
    for s in bt.SEASONS[1:]:
        year = nba_data.season_start_year(s)
        picks = draft[(draft.SEASON.astype(int) == year)].set_index("PERSON_ID").OVERALL_PICK
        g = pg[s].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"))
        ages = nba_data.player_ages(s).set_index("PLAYER_ID").AGE
        for pid, pick in picks.items():
            if pid in g.index and g.loc[pid].n >= 10 and pid in ages.index:
                rows.append({"season": s, "PLAYER_ID": pid, "bucket": bpv.pick_bucket(pick), "pick": pick,
                             "age": ages[pid], "fp": g.loc[pid].fp})
    d = pd.DataFrame(rows)
    scored = []
    for s in d.season.unique():
        tr, te = d[d.season != s], d[d.season == s].copy()
        base = tr.groupby("bucket").fp.mean()
        te["base"] = te.bucket.map(base)
        resid = tr.fp - tr.bucket.map(base)
        x = tr.age - tr.age.mean()
        slope = float((x * resid).sum() / (x ** 2).sum())
        te["new"] = te.base + slope * (te.age - tr.age.mean())
        te["slope"] = slope
        scored.append(te)
    t = pd.concat(scored, ignore_index=True)
    t["key"] = t.PLAYER_ID.astype(str)
    b = tm.boot(t, np.abs(t.new - t.fp), np.abs(t.base - t.fp), key="key")
    return {"n": len(t), "slope_fpts_per_year_of_age": [round(float(v), 2) for v in sorted(t.slope.unique())],
            "mae_draft_slot": bt.mae(t.base, t.fp), "mae_with_age": bt.mae(t.new, t.fp), "new_minus_current": b,
            "verdict": tm.verdict(b)}


def r6(pg, tg):
    """Known long-term absences (as in test_misc T4): flat boost vs usage-weighted boost."""
    rows = []
    for s in bt.TRAIN + bt.TEST:
        g_all = add_components(pg[s]).sort_values("GAME_DATE")
        sched = {t: sorted(x) for t, x in tg[s].groupby("TEAM_ID").GAME_DATE}
        by_player = {pid: g for pid, g in g_all.groupby("PLAYER_ID")}
        for c in bt.checkpoints(g_all, 28):
            before, after = g_all[g_all.GAME_DATE < c], g_all[g_all.GAME_DATE >= c]
            st_all = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"),
                                                     team=("TEAM_ID", "last"), last=("GAME_DATE", "max"),
                                                     use=("USE", "sum"), mins=("MIN", "sum"))
            st_all["use_rate"] = st_all.use / st_all.mins.clip(lower=1)
            after_n = after.groupby("PLAYER_ID").size()
            lost = {}
            for pid, st in st_all[(st_all.mpg >= 20) & (st_all.n >= 10)].iterrows():
                sch = sched[st.team]
                j = bisect_left(sch, c)
                remaining = len(sch) - j
                if remaining < 10 or j < 3 or st["last"] >= sch[j - 3]:
                    continue
                if after_n.get(pid, 0) <= 0.1 * remaining:
                    lost[st.team] = lost.get(st.team, 0.0) + st.mpg
            team_use = st_all[st_all.n >= 10].groupby("team").use_rate.mean()
            for pid, st in st_all[(st_all.n >= 10) & (st_all.mpg >= 12)].iterrows():
                if after_n.get(pid, 0) < 10 or st.team not in lost:
                    continue
                g = by_player[pid]
                l5 = g[g.GAME_DATE < c].tail(5)
                pm = st.fp / max(st.mpg, 1)
                dm = pm * (l5.MIN.mean() - st.mpg)
                pred = st.fp + 0.3 * dm + 0.1 * (l5.FPTS.mean() - st.fp - dm)
                rows.append({"season": s, "PLAYER_ID": pid, "pred": pred, "A": g[g.GAME_DATE >= c].FPTS.mean(),
                             "lost": lost[st.team], "rel_use": st.use_rate / team_use[st.team]})
    d = pd.DataFrame(rows)
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)
    res = {"n_affected_train": len(tr), "n_affected_test": len(te)}
    fits = {}
    for label, xtr, xte in [("flat", tr.lost, te.lost), ("usage_weighted", tr.lost * tr.rel_use, te.lost * te.rel_use)]:
        b = float((xtr * (tr.A - tr.pred)).sum() / (xtr ** 2).sum())
        fits[label] = te.pred + b * xte
        res[f"{label}_coef"] = b
    bb = tm.boot(te, np.abs(fits["usage_weighted"] - te.A), np.abs(fits["flat"] - te.A))
    res["usage_minus_flat"] = bb
    res["verdict"] = tm.verdict(bb)
    return res


def main():
    pg, tg = bt.load()
    res = r1_r2(pg, tg)
    print("R1/R2", json.dumps(res, default=float), flush=True)
    res["R3"] = r3(pg, tg)
    print("R3", json.dumps(res["R3"]), flush=True)
    res["R4"] = r4(pg, tg)
    print("R4", json.dumps(res["R4"]), flush=True)
    res["R5"] = r5(pg)
    print("R5", json.dumps(res["R5"]), flush=True)
    res["R6"] = r6(pg, tg)
    print("R6", json.dumps(res["R6"]), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
