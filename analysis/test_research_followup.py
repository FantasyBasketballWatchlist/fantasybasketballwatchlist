"""Follow-ups to test_research_ideas.py.

Run:  python -m analysis.test_research_followup    (writes analysis/test_research_followup.json)

F1  Per-stat stabilization (R1) rerun with a guard for zero-minute rows.
F2  Why does BPV under-predict rest-of-season production (R3)? Residuals by age and projection
    level; how much comes from scoring only players who kept playing (10+ games after)?
    Then test an in-season age drift (by age bucket, fitted on 2021-22..2024-25) vs the generic
    recalibration, on 2025-26.
F3  Tanking as a prediction: a player's fantasy-playoff FPTS total, with games-played share
    (and FPTS/game) adjusted by his team's status two weeks before the window (bad <= .35 wins,
    top >= .68), fitted leave-one-season-out, vs no adjustment.
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_misc as tm
from analysis import test_research_ideas as ri
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_research_followup.json")


def padded_prediction(d, pads, k_min):
    mpg = bpv.shrink(d.mins / d.n, d.n, d.prev_mpg, k_min)
    total = 0
    for k in ri.COMP_COLS:
        rate = (d[f"cur_{k}"] + pads[k] * d[f"prev_rate_{k}"]) / (d.mins + pads[k]).clip(lower=1)
        total = total + ri.COMP_W[k] * rate
    return total * mpg


def f1(pg, tg):
    d = ri.early_rows(pg, tg)
    d = d[d.mins > 0]
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)
    base_te = bpv.shrink(te.S, te.n, te.prev_fp, 8)
    grid = [0, 50, 100, 200, 400, 800, 1600, 3200]
    pads, k_min = {k: 400 for k in ri.COMP_COLS}, 4
    for _ in range(3):
        k_min = min([0, 1, 2, 4, 8, 16], key=lambda km: bt.mae(padded_prediction(tr, pads, km), tr.A))
        for k in ri.COMP_COLS:
            pads[k] = min(grid, key=lambda x: bt.mae(padded_prediction(tr, {**pads, k: x}, k_min), tr.A))
    new = padded_prediction(te, pads, k_min)
    b = tm.boot(te, np.abs(new - te.A), np.abs(base_te - te.A))
    early = (te.n <= 20).to_numpy()
    be = tm.boot(te[early].reset_index(drop=True), np.abs(new[early] - te.A[early]).to_numpy(),
                 np.abs(base_te[early] - te.A[early]).to_numpy())
    return {"paddings_minutes": pads, "minutes_k_games": k_min, "mae_current": bt.mae(base_te, te.A),
            "mae_padded": bt.mae(new, te.A), "padded_minus_current": b, "verdict": tm.verdict(b),
            "first_20_games": be, "verdict_first_20": tm.verdict(be), "n_test": len(te)}


def f2(pg, tg):
    frames = []
    for s in bt.TRAIN + bt.TEST:
        for min_after in (10, 1):
            cp = bt.checkpoint_rows(s, pg[s], tg[s], min_after=min_after)
            cp["min_after"] = min_after
            frames.append(cp)
    cp = pd.concat(frames, ignore_index=True)
    cp = cp[cp.mpg_S >= 12].copy()
    per_min = cp.S / cp.mpg_S.clip(lower=1)
    dm = per_min * (cp.mpg_L5 - cp.mpg_S)
    cp["pred"] = cp.S + 0.3 * dm + 0.1 * (cp.L5 - cp.S - dm)
    cp["resid"] = cp.A_ros - cp.pred
    ages = pd.concat([nba_data.player_ages(s).assign(season=s) for s in bt.TRAIN + bt.TEST])
    cp = cp.merge(ages[["PLAYER_ID", "season", "AGE"]], on=["PLAYER_ID", "season"], how="left")
    cp["bucket"] = cp.AGE.map(lambda a: bpv.age_bucket(a) if pd.notna(a) else "unknown")
    main = cp[cp.min_after == 10]
    res = {"mean_residual_10plus_games_after": float(main.resid.mean()),
           "mean_residual_1plus_games_after": float(cp[cp.min_after == 1].resid.mean()),
           "residual_by_age": main.groupby("bucket").resid.agg(["mean", "size"]).round(3).to_dict("index"),
           "residual_by_projection_quintile": main.groupby(pd.qcut(main.pred, 5)).resid.mean().round(3)
                                                 .rename(index=str).to_dict()}
    tr, te = main[main.season.isin(bt.TRAIN)], main[main.season.isin(bt.TEST)].reset_index(drop=True)
    drift = tr.groupby("bucket").resid.mean()
    age_new = te.pred + te.bucket.map(drift).fillna(0)
    b_age = tm.boot(te, np.abs(age_new - te.A_ros), np.abs(te.pred - te.A_ros))
    slope, icpt = np.polyfit(tr.pred, tr.A_ros, 1)
    rec = icpt + slope * te.pred
    b_rec = tm.boot(te, np.abs(rec - te.A_ros), np.abs(te.pred - te.A_ros))
    b_age_vs_rec = tm.boot(te, np.abs(age_new - te.A_ros), np.abs(rec - te.A_ros))
    res.update({"age_drift_by_bucket": drift.round(3).to_dict(),
                "age_drift_minus_current": b_age, "verdict_age_drift": tm.verdict(b_age),
                "recalibration_minus_current": b_rec, "verdict_recalibration": tm.verdict(b_rec),
                "age_drift_minus_recalibration": b_age_vs_rec})
    return res


def f3(pg, tg):
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
        win = g[g.GAME_DATE >= start].groupby("PLAYER_ID").FPTS.agg(["sum", "size"])
        team_games = t[t.GAME_DATE >= start].groupby("TEAM_ID").size()
        team_before = t[t.GAME_DATE < cut].groupby("TEAM_ID").size()
        ages = nba_data.player_ages(s).set_index("PLAYER_ID").AGE
        for pid, b in before[(before.mpg >= 20) & (before.n >= 30)].iterrows():
            w_sum, w_n = (win.loc[pid, "sum"], win.loc[pid, "size"]) if pid in win.index else (0.0, 0)
            rows.append({"season": s, "PLAYER_ID": pid, "status": status[b.team], "vet": ages.get(pid, 0) >= 28,
                         "fp": b.fp, "share": b.n / team_before[b.team], "games": team_games[b.team],
                         "actual": w_sum, "share_w": w_n / team_games[b.team],
                         "fp_w": (w_sum / w_n) if w_n else np.nan})
    d = pd.DataFrame(rows)
    d["group"] = d.status + np.where(d.vet, "_vet", "_young")
    scored = []
    for s in d.season.unique():
        tr, te = d[d.season != s], d[d.season == s].copy()
        delta_share = (tr.share_w - tr.share).groupby(tr.group).mean()
        ratio_fp = (tr.fp_w / tr.fp).groupby(tr.group).median()
        mid_share = (tr.share_w - tr.share)[tr.status == "middle"].mean()
        te["base"] = te.fp * te.share * te.games
        te["base_mid"] = te.fp * (te.share + mid_share) * te.games          # league-wide late-season drop only
        te["adj"] = te.fp * te.group.map(ratio_fp).fillna(1) * (te.share + te.group.map(delta_share).fillna(mid_share)).clip(0, 1) * te.games
        scored.append(te)
    t = pd.concat(scored, ignore_index=True)
    t["key"] = t.PLAYER_ID.astype(str) + t.season
    b1 = tm.boot(t, np.abs(t.adj - t.actual), np.abs(t.base_mid - t.actual), key="key")
    b0 = tm.boot(t, np.abs(t.base_mid - t.actual), np.abs(t.base - t.actual), key="key")
    per_season = {s: float((np.abs(g.adj - g.actual) - np.abs(g.base_mid - g.actual)).mean()) for s, g in t.groupby("season")}
    fit_all = {"share_change_by_group": (d.share_w - d.share).groupby(d.group).mean().round(3).to_dict(),
               "fpts_ratio_by_group": (d.fp_w / d.fp).groupby(d.group).median().round(3).to_dict(),
               "n_by_group": d.group.value_counts().to_dict()}
    return {"n": len(t), "mae_no_adjustment": bt.mae(t.base, t.actual), "mae_league_drop_only": bt.mae(t.base_mid, t.actual),
            "mae_status_adjusted": bt.mae(t.adj, t.actual), "league_drop_minus_none": b0,
            "status_minus_league_drop": b1, "verdict": tm.verdict(b1), "per_season_diff": per_season, "fit_all": fit_all}


def main():
    pg, tg = bt.load()
    res = {"F1": f1(pg, tg)}
    print("F1", json.dumps(res["F1"], default=float), flush=True)
    res["F2"] = f2(pg, tg)
    print("F2", json.dumps(res["F2"], default=float), flush=True)
    res["F3"] = f3(pg, tg)
    print("F3", json.dumps(res["F3"], default=float), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
