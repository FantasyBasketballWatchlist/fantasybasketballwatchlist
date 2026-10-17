"""What do the official NBA injury reports add? (2021-22..2025-26, one report per game day)

Run:  python -m analysis.test_injury_reports     (writes analysis/test_injury_reports.json)

I1  Why regulars miss games: injury vs rest vs G League vs personal, from report reasons.
I2  Status conversion: how often Probable / Questionable / Doubtful players actually play.
I3  Automatic long-term detection. At weekly checkpoints, a 20+ mpg player listed Out on the
    latest report with a serious injury (surgery, tear, fracture, rupture, ACL, Achilles...)
    is flagged. (a) How often do flagged players miss most of the rest of the season?
    (b) Teammate boost from flagged players (coefficient fitted on 2021-22..2024-25, scored on
    2025-26) vs current BPV, for rest-of-season FPTS/game. No hindsight is used.
    (c) The flagged player's own rest-of-season availability: flag-based estimate vs BPV's.
I4  Season availability: do last season's injury and rest absences improve next season's
    availability estimate over BPV's current one? Leave-one-season-out, 2022-23..2025-26.
I5  Traits: are injury absences' long-vs-scattered pattern and resting stable year to year?
"""
import json
import os
import re
import warnings
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import robustness as rb
from analysis import test_misc as tm
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_injury_reports.json")
SERIOUS = bpv.SERIOUS_INJURY


category = bpv.absence_reason


def report_name(name):
    """'Bagley III, Marvin' -> normalized 'marvin bagley iii'."""
    return ratings.normalize_name(bpv.report_player_name(name))


def load_reports(pg):
    frames, unmatched = [], {}
    for s in SEASONS:
        r = nba_data.injury_reports(s).copy()
        ids = {}
        for pid, n in pg[s].drop_duplicates("PLAYER_ID").set_index("PLAYER_ID").PLAYER_NAME.items():
            ids[ratings.normalize_name(n)] = pid
        r["key"] = r["Player Name"].map(report_name)
        r["PLAYER_ID"] = r.key.map(ids)
        unmatched[s] = float(r.PLAYER_ID.isna().mean())
        r["season"] = s
        r["category"] = r.Reason.map(category)
        r["serious"] = r.Reason.fillna("").str.contains(SERIOUS)
        r["GAME_DATE"] = pd.to_datetime(r["Game Date"], format="%m/%d/%Y", errors="coerce").dt.strftime("%Y-%m-%d")
        frames.append(r.dropna(subset=["PLAYER_ID", "GAME_DATE"]))
    rep = pd.concat(frames, ignore_index=True)
    rep["PLAYER_ID"] = rep.PLAYER_ID.astype(int)
    # One row per player per game date (a report can list the same game twice across updates).
    rep = rep.sort_values("REPORT_DATE").drop_duplicates(["PLAYER_ID", "GAME_DATE"], keep="last")
    return rep, unmatched


def i1_i2(pg, rep):
    played = {s: set(zip(pg[s].PLAYER_ID, pg[s].GAME_DATE)) for s in SEASONS}
    mpg = {s: pg[s].groupby("PLAYER_ID").MIN.mean() for s in SEASONS}
    rep = rep.copy()
    rep["played"] = [(p, d) in played[s] for p, d, s in zip(rep.PLAYER_ID, rep.GAME_DATE, rep.season)]
    rep["mpg"] = [mpg[s].get(p, 0) for p, s in zip(rep.PLAYER_ID, rep.season)]
    reg_out = rep[(rep["Current Status"] == "Out") & (rep.mpg >= 20) & ~rep.played]
    reasons = reg_out.category.value_counts(normalize=True).round(4).to_dict()
    by_season = reg_out.groupby("season").category.value_counts(normalize=True).unstack().round(3).fillna(0).to_dict("index")
    conv = rep.groupby("Current Status").played.agg(["mean", "size"]).round(3).to_dict("index")
    return {"regulars_out_games_by_reason": reasons, "by_season": by_season,
            "status_played_share": conv, "report_rows": len(rep)}, rep


def i3(pg, tg, rep):
    rows, flags = [], []
    for s in [x for x in SEASONS if x in bt.TRAIN + bt.TEST]:
        g_all = pg[s].sort_values("GAME_DATE")
        sched = {t: sorted(x) for t, x in tg[s].groupby("TEAM_ID").GAME_DATE}
        by_player = {pid: g for pid, g in g_all.groupby("PLAYER_ID")}
        rs = rep[rep.season == s]
        report_dates = sorted(rs.REPORT_DATE.unique())
        for c in bt.checkpoints(g_all, 28):
            j = bisect_left(report_dates, c) - 1
            if j < 0:
                continue
            latest = rs[rs.REPORT_DATE == report_dates[j]]
            out_serious = set(latest[(latest["Current Status"] == "Out") & latest.serious & (latest.category == "injury")].PLAYER_ID)
            out_any = set(latest[(latest["Current Status"] == "Out") & (latest.category == "injury")].PLAYER_ID)
            before, after = g_all[g_all.GAME_DATE < c], g_all[g_all.GAME_DATE >= c]
            st_all = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"),
                                                     team=("TEAM_ID", "last"))
            after_n = after.groupby("PLAYER_ID").size()
            lost_serious, lost_any = {}, {}
            for pid, st in st_all[(st_all.mpg >= 20) & (st_all.n >= 10)].iterrows():
                remaining = len(sched[st.team]) - bisect_left(sched[st.team], c)
                if remaining < 10:
                    continue
                share_played = after_n.get(pid, 0) / remaining
                if pid in out_any:
                    flags.append({"season": s, "PLAYER_ID": pid, "serious": pid in out_serious,
                                  "share_played_rest": share_played, "remaining": remaining})
                if pid in out_serious:
                    lost_serious[st.team] = lost_serious.get(st.team, 0.0) + st.mpg
                if pid in out_any:
                    lost_any[st.team] = lost_any.get(st.team, 0.0) + st.mpg
            for pid, st in st_all[(st_all.n >= 10) & (st_all.mpg >= 12)].iterrows():
                if after_n.get(pid, 0) < 10 or pid in out_any:
                    continue
                g = by_player[pid]
                l5 = g[g.GAME_DATE < c].tail(5)
                pm = st.fp / max(st.mpg, 1)
                dm = pm * (l5.MIN.mean() - st.mpg)
                pred = st.fp + 0.3 * dm + 0.1 * (l5.FPTS.mean() - st.fp - dm)
                rows.append({"season": s, "PLAYER_ID": pid, "pred": pred, "A": g[g.GAME_DATE >= c].FPTS.mean(),
                             "lost_serious": lost_serious.get(st.team, 0.0), "lost_any": lost_any.get(st.team, 0.0)})
    d, f = pd.DataFrame(rows), pd.DataFrame(flags)
    res = {"flags": {
        "serious_n": int(f.serious.sum()), "other_out_n": int((~f.serious).sum()),
        "serious_mean_share_played_rest": float(f[f.serious].share_played_rest.mean()),
        "serious_share_missing_80pct_plus": float((f[f.serious].share_played_rest <= 0.2).mean()),
        "other_mean_share_played_rest": float(f[~f.serious].share_played_rest.mean()),
        "other_share_missing_80pct_plus": float((f[~f.serious].share_played_rest <= 0.2).mean()),
    }}
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)
    for col in ("lost_serious", "lost_any"):
        b = float((tr[col] * (tr.A - tr.pred)).sum() / (tr[col] ** 2).sum())
        new = te.pred + b * te[col]
        all_ = tm.boot(te, np.abs(new - te.A), np.abs(te.pred - te.A))
        sub = te[te[col] > 0].reset_index(drop=True)
        aff = tm.boot(sub, np.abs(sub.pred + b * sub[col] - sub.A), np.abs(sub.pred - sub.A))
        res[col] = {"coef": b, "all": all_, "affected": aff, "n_affected_test": len(sub),
                    "verdict_all": tm.verdict(all_), "verdict_affected": tm.verdict(aff)}
    # (c) Own availability for the rest of the season: fitted share by flag type vs BPV's season-long estimate.
    ftr, fte = f[f.season.isin(bt.TRAIN)], f[f.season.isin(bt.TEST)]
    share = ftr.groupby("serious").share_played_rest.median().to_dict()
    res["own_availability_rest_of_season"] = {
        "train_median_share_played": {str(k): float(v) for k, v in share.items()},
        "test_mae_flag_estimate": bt.mae(fte.serious.map(share), fte.share_played_rest),
        "test_mae_assume_league_avg_0.74": bt.mae(np.full(len(fte), 0.74), fte.share_played_rest),
        "n_test": len(fte),
    }
    return res


def season_absences(pg, tg, rep):
    """Per player-season: games missed for injury and for rest (report says Out and he didn't play)."""
    played = {s: set(zip(pg[s].PLAYER_ID, pg[s].GAME_DATE)) for s in SEASONS}
    out = rep[rep["Current Status"].isin(["Out"])].copy()
    out["played"] = [(p, d) in played[s] for p, d, s in zip(out.PLAYER_ID, out.GAME_DATE, out.season)]
    out = out[~out.played]
    return out.groupby(["season", "PLAYER_ID", "category"]).size().unstack(fill_value=0)


def i4(pg, tg, rep):
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    ab = season_absences(pg, tg, rep)
    rows = []
    for t in SEASONS[1:]:
        prev = SEASONS[SEASONS.index(t) - 1]
        p_league, _ = rb.league_before(hist, t)
        p_hat = bpv.predict_availability(hist, bt.SEASONS, prev, 0.5, 123, p_league)
        hp = hist[(hist.season == prev) & (hist.mpg >= 20) & (hist.played >= 20)].set_index("PLAYER_ID")
        ht = hist[hist.season == t].set_index("PLAYER_ID")
        for pid in hp.index.intersection(ht.index):
            a = ab.loc[(prev, pid)] if (prev, pid) in ab.index else pd.Series(dtype=float)
            rows.append({"target": t, "PLAYER_ID": pid, "availability": float(ht.loc[pid].availability),
                         "p_hat": float(p_hat.get(pid, p_league)),
                         "inj_prev": float(a.get("injury", 0)) / float(hp.loc[pid].possible),
                         "rest_prev": float(a.get("rest", 0)) / float(hp.loc[pid].possible)})
    d = pd.DataFrame(rows)
    shifts = np.round(np.arange(-0.6, 0.61, 0.05), 2)
    scored = []
    for t in SEASONS[1:]:
        tr, te = d[d.target != t], d[d.target == t].copy()
        best = min(((a, b) for a in shifts for b in shifts),
                   key=lambda ab_: bt.mae(np.clip(tr.p_hat + ab_[0] * (tr.inj_prev - tr.inj_prev.median())
                                                  + ab_[1] * (tr.rest_prev - tr.rest_prev.median()), 0, 1), tr.availability))
        te["new"] = np.clip(te.p_hat + best[0] * (te.inj_prev - tr.inj_prev.median())
                            + best[1] * (te.rest_prev - tr.rest_prev.median()), 0, 1)
        te["coefs"] = str(best)
        scored.append(te)
    s = pd.concat(scored, ignore_index=True)
    s["key"] = s.PLAYER_ID.astype(str) + s.target
    b = tm.boot(s, np.abs(s.new - s.availability), np.abs(s.p_hat - s.availability), key="key")
    return {"n": len(s), "mae_current": bt.mae(s.p_hat, s.availability), "mae_with_report_features": bt.mae(s.new, s.availability),
            "new_minus_current": b, "verdict": tm.verdict(b), "coefs_by_fold": sorted(set(s.coefs))}


def i5(pg, tg, rep):
    ab = season_absences(pg, tg, rep)
    mpg = {s: pg[s].groupby("PLAYER_ID").MIN.mean() for s in SEASONS}
    res = {}
    rest = ab.get("rest", pd.Series(0, index=ab.index))
    pairs = []
    for a, b in zip(SEASONS, SEASONS[1:]):
        for pid in mpg[a][mpg[a] >= 25].index.intersection(mpg[b][mpg[b] >= 25].index):
            pairs.append((rest.get((a, pid), 0), rest.get((b, pid), 0)))
    p = np.array(pairs, dtype=float)
    res["rest_games_yoy_corr_25mpg"] = float(np.corrcoef(p.T)[0, 1])
    res["rest_pairs"] = len(p)
    res["rest_games_mean_per_season_25mpg"] = float(p[:, 0].mean())
    return res


def main():
    pg, tg = bt.load()
    rep, unmatched = load_reports(pg)
    res = {"unmatched_name_share": unmatched}
    res["I1_I2"], rep2 = i1_i2(pg, rep)
    print("I1/I2", json.dumps(res["I1_I2"])[:1500], flush=True)
    res["I3"] = i3(pg, tg, rep)
    print("I3", json.dumps(res["I3"]), flush=True)
    res["I4"] = i4(pg, tg, rep)
    print("I4", json.dumps(res["I4"]), flush=True)
    res["I5"] = i5(pg, tg, rep)
    print("I5", json.dumps(res["I5"]), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=str)


if __name__ == "__main__":
    main()
