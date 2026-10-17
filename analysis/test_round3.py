"""Round 3 of candidate improvements, each scored against current BPV out of sample.

Run:  python -m analysis.test_round3        (writes analysis/test_round3.json)

P1  Preseason minutes: does a player's preseason minutes per game (2+ preseason games) predict his
    season beyond last season + age + roster crowding? Also for rookies vs the draft-slot baseline.
P2  Return timelines by injury type: for regulars listed Out with an injury, predict the share of
    remaining games played from the injury type (serious / sprain / strain / soreness / illness /
    other) instead of the current rule (serious -> 7%, otherwise BPV's usual availability).
P3  Team minutes adding up: scale last season's production by the team's rotation size
    (league-average rotation minutes / team rotation minutes) ^ alpha, instead of additive crowding.
P4  Weekly totals: predict each regular's fantasy points for a Monday-Sunday week using the latest
    injury report status before the week, vs using his season games-played share.
P5  One IR slot: draft simulations scored with streamed free-agent credit capped at one IR slot
    (82 games per team per season). Does BPV's streaming credit (q = league share) still draft
    better than no credit (q = 0) or half credit?
Leave-one-season-out unless stated; 95% intervals resample whole players.
"""
import datetime as dt
import json
import os
import random
import warnings
from bisect import bisect_left
from collections import defaultdict

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp
from analysis import test_injury_reports as ti
from analysis import test_minutes_model as tmm
from analysis import test_misc as tm
from analysis import robustness as rb
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_round3.json")
CROWDING_COEF = -0.0177


def boot_key(df, e_new, e_old, key):
    return tm.boot(df.assign(_k=key), np.asarray(e_new), np.asarray(e_old), key="_k")


def preseason_frames(pg):
    tab = pp.season_table(pg)
    frames = {}
    for t in pp.TARGETS:
        f = pp.frame(tab, t)
        ctx = tmm.roster_context(pg, t)
        f = f.merge(ctx[["crowding", "crowding_raw"]], left_on="PLAYER_ID", right_index=True, how="left")
        f["crowding"] = f.crowding.fillna(0)
        pre = bpv.add_fpts(nba_data.preseason_game_logs(t)).groupby("PLAYER_ID").agg(
            pre_n=("FPTS", "size"), pre_mpg=("MIN", "mean"))
        f = f.merge(pre, left_on="PLAYER_ID", right_index=True, how="left")
        f["pre_n"] = f.pre_n.fillna(0)
        frames[t] = f
    return frames


def p1_p3(pg):
    frames = preseason_frames(pg)
    scored = []
    for t in pp.TARGETS:
        tr = pd.concat([frames[x] for x in pp.TARGETS if x != t], ignore_index=True)
        te = frames[t].copy()
        for d in (tr, te):
            d["last"] = d.fp1
        curve = pp.fit_age_curve(tr, "last")
        for d in (tr, te):
            d["age_pred"] = pp.with_age(d, "last", curve)
            d["base"] = d.age_pred + CROWDING_COEF * d.crowding
            fpm = d.fp1 / d.mpg1.clip(lower=1)
            dmin = np.where(d.pre_n >= 2, d.pre_mpg - d.mpg1, 0.0)
            d["x_up"] = fpm * np.clip(dmin, 0, None)
            d["x_down"] = fpm * np.clip(dmin, None, 0)
        # P1: minutes change seen in preseason (up and down fitted separately).
        X = tr[["x_up", "x_down"]].to_numpy()
        coef, *_ = np.linalg.lstsq(X, (tr.actual - tr.base).to_numpy(), rcond=None)
        te["pre"] = te.base + te[["x_up", "x_down"]].to_numpy() @ coef
        te["pre_coef"] = str([round(c, 3) for c in coef])
        # P3: multiplicative rotation scaling instead of additive crowding.
        mean_rot = tr.crowding_raw.mean()
        def scaled(d, a):
            ratio = (mean_rot / d.crowding_raw.clip(lower=1)).where(d.crowding_raw.notna(), 1.0)
            return d.age_pred * ratio ** a
        alphas = np.round(np.arange(0, 0.61, 0.05), 2)
        a_best = min(alphas, key=lambda a: bt.mae(scaled(tr, a), tr.actual))
        te["scaled"] = scaled(te, a_best)
        te["alpha"] = a_best
        scored.append(te)
    d = pd.concat(scored, ignore_index=True)
    key = d.PLAYER_ID.astype(str) + d.target
    has_pre = (d.pre_n >= 2).to_numpy()
    b1 = boot_key(d, np.abs(d.pre - d.actual), np.abs(d.base - d.actual), key)
    sub = d[has_pre].reset_index(drop=True)
    b1s = boot_key(sub, np.abs(sub.pre - sub.actual), np.abs(sub.base - sub.actual), key[has_pre].reset_index(drop=True))
    b3 = boot_key(d, np.abs(d.scaled - d.actual), np.abs(d.base - d.actual), key)
    res = {"P1": {"n": len(d), "share_with_preseason": float(has_pre.mean()), "coefs_by_fold_up_down": sorted(set(d.pre_coef)),
                  "mae_current": bt.mae(d.base, d.actual), "mae_with_preseason": bt.mae(d.pre, d.actual),
                  "minus_current": b1, "verdict": tm.verdict(b1), "players_with_preseason": b1s},
           "P3": {"alphas_by_fold": sorted(set(float(a) for a in d.alpha)), "mae_scaled": bt.mae(d.scaled, d.actual),
                  "scaled_minus_additive_crowding": b3, "verdict": tm.verdict(b3)}}
    res["P1_rookies"] = p1_rookies(pg)
    return res


def p1_rookies(pg):
    draft = nba_data.draft_history()
    rows = []
    for s in pp.TARGETS:
        year = nba_data.season_start_year(s)
        picks = draft[draft.SEASON.astype(int) == year].set_index("PERSON_ID").OVERALL_PICK
        g = pg[s].groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"))
        pre = nba_data.preseason_game_logs(s).groupby("PLAYER_ID").agg(pre_n=("MIN", "size"), pre_mpg=("MIN", "mean"))
        for pid, pick in picks.items():
            if pid in g.index and g.loc[pid].n >= 10:
                pr = pre.loc[pid] if pid in pre.index else None
                rows.append({"season": s, "PLAYER_ID": pid, "bucket": bpv.pick_bucket(pick), "fp": g.loc[pid].fp,
                             "pre_mpg": pr.pre_mpg if pr is not None and pr.pre_n >= 2 else np.nan})
    d = pd.DataFrame(rows)
    out = []
    for s in d.season.unique():
        tr, te = d[d.season != s], d[d.season == s].copy()
        base = tr.groupby("bucket").fp.mean()
        bmpg = tr.groupby("bucket").pre_mpg.mean()
        tr_x = (tr.pre_mpg - tr.bucket.map(bmpg)).fillna(0)
        slope = float((tr_x * (tr.fp - tr.bucket.map(base))).sum() / (tr_x ** 2).sum())
        te["base"] = te.bucket.map(base)
        te["new"] = te.base + slope * (te.pre_mpg - te.bucket.map(bmpg)).fillna(0)
        te["slope"] = slope
        out.append(te)
    t = pd.concat(out, ignore_index=True)
    b = boot_key(t, np.abs(t.new - t.fp), np.abs(t.base - t.fp), t.PLAYER_ID.astype(str))
    return {"n": len(t), "slopes": sorted(set(round(x, 3) for x in t.slope)), "mae_draft_slot": bt.mae(t.base, t.fp),
            "mae_with_preseason": bt.mae(t.new, t.fp), "minus_current": b, "verdict": tm.verdict(b)}


INJURY_TYPES = [("sprain", "sprain"), ("strain", "strain"),
                ("soreness", "soreness|tendin|contusion|bruise|inflammation|spasm|tightness|sore|irritation|impingement"),
                ("illness", "illness|n/a")]


def injury_type(reason):
    r = str(reason).lower()
    if bpv.SERIOUS_INJURY.search(r):
        return "serious"
    for name, pattern in INJURY_TYPES:
        if pd.Series([r]).str.contains(pattern).iloc[0]:
            return name
    return "other"


def p2(pg, tg, rep, hist):
    rows = []
    for s in ti.SEASONS:
        if s not in bt.SEASONS[1:]:
            continue
        g_all = pg[s].sort_values("GAME_DATE")
        sched = {t: sorted(x) for t, x in tg[s].groupby("TEAM_ID").GAME_DATE}
        rs = rep[rep.season == s]
        dates = sorted(rs.REPORT_DATE.unique())
        p_league, _ = rb.league_before(hist, s)
        prev = bt.SEASONS[bt.SEASONS.index(s) - 1]
        p_hat = bpv.predict_availability(hist, bt.SEASONS, prev, 0.5, 123, p_league)
        for c in bt.checkpoints(g_all, 28):
            j = bisect_left(dates, c) - 1
            if j < 0:
                continue
            latest = rs[(rs.REPORT_DATE == dates[j]) & (rs["Current Status"] == "Out") & (rs.category == "injury")]
            reason = dict(zip(latest.PLAYER_ID, latest.Reason))
            before = g_all[g_all.GAME_DATE < c]
            after_n = g_all[g_all.GAME_DATE >= c].groupby("PLAYER_ID").size()
            st = before.groupby("PLAYER_ID").agg(n=("FPTS", "size"), mpg=("MIN", "mean"), team=("TEAM_ID", "last"))
            for pid, r in st[(st.mpg >= 20) & (st.n >= 10)].iterrows():
                if pid not in reason:
                    continue
                rem = len(sched[r.team]) - bisect_left(sched[r.team], c)
                if rem < 10:
                    continue
                rows.append({"season": s, "PLAYER_ID": pid, "type": injury_type(reason[pid]),
                             "share": after_n.get(pid, 0) / rem, "p_hat": float(p_hat.get(pid, p_league))})
    d = pd.DataFrame(rows)
    out = []
    for s in d.season.unique():
        tr, te = d[d.season != s], d[d.season == s].copy()
        med = tr.groupby("type").share.median()
        serious_med = med.get("serious", 0.07)
        te["current"] = np.where(te.type == "serious", serious_med, te.p_hat)
        te["new"] = te.type.map(med).fillna(te.p_hat)
        out.append(te)
    t = pd.concat(out, ignore_index=True)
    key = t.PLAYER_ID.astype(str) + t.season
    b = boot_key(t, np.abs(t.new - t.share), np.abs(t.current - t.share), key)
    return {"n": len(t), "by_type": d.groupby("type").share.agg(["median", "mean", "size"]).round(3).to_dict("index"),
            "mae_current_rule": bt.mae(t.current, t.share), "mae_by_type": bt.mae(t.new, t.share),
            "minus_current": b, "verdict": tm.verdict(b)}


def p4(pg, tg, rep):
    rows = []
    for s in ti.SEASONS:
        g_all = pg[s].sort_values("GAME_DATE")
        tgs = tg[s]
        rs = rep[rep.season == s]
        dates = sorted(rs.REPORT_DATE.unique())
        first = dt.date.fromisoformat(g_all.GAME_DATE.min())
        monday = first + dt.timedelta(days=(7 - first.weekday()) % 7 + 21)
        last = dt.date.fromisoformat(g_all.GAME_DATE.max())
        while monday + dt.timedelta(days=6) <= last:
            ws, we = monday.isoformat(), (monday + dt.timedelta(days=7)).isoformat()
            j = bisect_left(dates, ws) - 1          # latest report before the week starts
            latest = rs[rs.REPORT_DATE == dates[j]] if j >= 0 else rs.iloc[0:0]
            status = {}
            for pid, stt, cat, ser in zip(latest.PLAYER_ID, latest["Current Status"], latest.category, latest.serious):
                status[pid] = "out_serious" if (stt == "Out" and ser) else f"{stt.lower()}_{cat}" if stt == "Out" else stt.lower()
            before = g_all[g_all.GAME_DATE < ws]
            week = g_all[(g_all.GAME_DATE >= ws) & (g_all.GAME_DATE < we)]
            team_before = tgs[tgs.GAME_DATE < ws].groupby("TEAM_ID").size()
            team_week = tgs[(tgs.GAME_DATE >= ws) & (tgs.GAME_DATE < we)].groupby("TEAM_ID").size()
            st = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"), team=("TEAM_ID", "last"))
            actual = week.groupby("PLAYER_ID").FPTS.sum()
            for pid, r in st[(st.mpg >= 20) & (st.n >= 10)].iterrows():
                gw = team_week.get(r.team, 0)
                if gw == 0:
                    continue
                rows.append({"season": s, "PLAYER_ID": pid, "fp": r.fp, "games": gw,
                             "share": min(r.n / team_before.get(r.team, r.n), 1.0),
                             "status": status.get(pid, "not_listed"), "actual": actual.get(pid, 0.0)})
            monday += dt.timedelta(days=7)
    d = pd.DataFrame(rows)
    d["played_share"] = 0.0
    tr, te = d[d.season.isin(bt.TRAIN)], d[d.season.isin(bt.TEST)].reset_index(drop=True)
    # Fitted: ratio of actual week total to (fp x games x share), by status.
    ratio = (tr.actual.groupby(tr.status).sum() / (tr.fp * tr.games * tr.share).groupby(tr.status).sum())
    te["base"] = te.fp * te.games * te.share
    te["new"] = te.base * te.status.map(ratio).fillna(1.0)
    b = tm.boot(te, np.abs(te.new - te.actual), np.abs(te.base - te.actual))
    listed = (te.status != "not_listed").to_numpy()
    bl = tm.boot(te[listed].reset_index(drop=True), np.abs(te.new[listed] - te.actual[listed]).to_numpy(),
                 np.abs(te.base[listed] - te.actual[listed]).to_numpy())
    return {"n_train": len(tr), "n_test": len(te), "ratio_by_status": ratio.round(3).to_dict(),
            "status_counts_test": te.status.value_counts().to_dict(),
            "mae_current": bt.mae(te.base, te.actual), "mae_with_report": bt.mae(te.new, te.actual),
            "minus_current": b, "verdict": tm.verdict(b), "listed_players_only": bl, "verdict_listed": tm.verdict(bl)}


def p5(pg, tg, hist):
    res = {}
    league_p, league_q = bpv.league_availability(hist)
    for target in pp.TARGETS:
        df, R = bt.preseason_frame(pg, hist, target, 0.5, 123, league_p, league_q, age_curve=bt.age_curve_before(pg, target))
        h_t = hist[hist.season == target].set_index("PLAYER_ID")
        df["missed_long"] = h_t.missed_long.reindex(df.index).fillna(0)
        R_t = bpv.replacement_level(hist[(hist.season == target) & (hist.played >= 20)].fpts_pg, 130)
        for q_label, q in [("q_league", league_q), ("q_half", league_q / 2), ("q_zero", 0.0)]:
            df[q_label] = bpv.bpv_value(df.S, df.p_hat, q, R)
        strategies = ["q_league", "q_half", "q_zero", "M5 80/20 x career GP%", "Last season total FPTS"]
        rng = random.Random(3)
        rankings = {s: df[s].sort_values(ascending=False).index.tolist() for s in strategies}
        totals = defaultdict(list)
        for _ in range(500):
            order = [s for s in strategies for _ in range(2)]
            rng.shuffle(order)
            taken, rosters = set(), defaultdict(list)
            for rnd in range(13):
                seq = range(10) if rnd % 2 == 0 else range(9, -1, -1)
                for seat in seq:
                    rank = rankings[order[seat]]
                    i = 0
                    while rank[i] in taken:
                        i += 1
                    taken.add(rank[i])
                    rosters[seat].append(rank[i])
            for seat, roster in rosters.items():
                played = df.loc[roster, "actual_total"].sum()
                streamed = min(df.loc[roster, "missed_long"].sum(), 82) * R_t     # one IR slot all season
                totals[order[seat]].append(played + streamed)
        res[target] = {s: float(np.mean(v)) for s, v in totals.items()}
    avg = {s: float(np.mean([res[t][s] for t in res])) for s in next(iter(res.values()))}
    wins = {s: sum(1 for t in res if max(res[t], key=res[t].get) == s) for s in avg}
    return {"by_season": res, "average": avg, "wins": wins}


def main():
    pg, tg = bt.load()
    res = p1_p3(pg)
    print("P1/P3", json.dumps(res, default=float), flush=True)
    rep, _ = ti.load_reports(pg)
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    res["P2"] = p2(pg, tg, rep, hist)
    print("P2", json.dumps(res["P2"], default=float), flush=True)
    res["P4"] = p4(pg, tg, rep)
    print("P4", json.dumps(res["P4"], default=float), flush=True)
    res["P5"] = p5(pg, tg, hist)
    print("P5", json.dumps(res["P5"], default=float), flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
