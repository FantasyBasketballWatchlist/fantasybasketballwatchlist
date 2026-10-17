"""Four more candidate improvements, each scored against current BPV out of sample.

Run:  python -m analysis.test_return_schedule     (prints results; set RETURN_SCHEDULE_OUT to save JSON)

C1  Post-injury return trajectory. Regulars (20+ mpg over 10+ games before) returning from 10+
    consecutive missed team games: minutes and FPTS/game in games 1-3, 4-10, 11+ after return vs the
    pre-absence level, by absence type (injury report). Then, at weekly checkpoints where the player
    returned within his last 10 games, do pre-absence-based projections beat the current method?
C2  2023-24 Player Participation Policy: did stars' (top 50 by prior-season FPTS/g) games-played share
    rise in 2023-24..2025-26 vs 2021-22..2022-23, relative to other regulars? Does a star adjustment
    fitted on 2023-24 improve availability predictions (decay 0.5, k 123) for 2024-25 / 2025-26?
C3  Weekly totals (test_round3.p4 design): back-to-back second games, minutes in the 3 days before the
    week, age 30+ and star status, on top of the status-factor method.
C4  Remaining schedule strength (opponents' fantasy points / points allowed per game to date) for
    rest-of-season FPTS/game; exact vs league-average remaining games for rest-of-season totals.

Adoption rule (set in advance): "better" only if the 95% player-cluster bootstrap interval excludes 0
in favor AND the candidate is better in the majority of held-out seasons.
Leave-one-season-out over 2021-22..2025-26 unless stated.
"""
import datetime as dt
import json
import os
import warnings
from bisect import bisect_left
from collections import Counter

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import robustness as rb
from analysis import test_injury_reports as ti
from analysis import test_misc as tm
import bpv
import nba_data

warnings.filterwarnings("ignore")
OUT = os.environ.get("RETURN_SCHEDULE_OUT")      # optional JSON output path
SEASONS = ["2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]
RECAL = (2.964, 0.910)
GAP = 10


def raw_pred(fp, mins):
    """Current in-season formula (before recalibration) from arrays of a player's games."""
    s, m = fp.mean(), mins.mean()
    l5, lm = fp[-5:].mean(), mins[-5:].mean()
    dm = (s / max(m, 1)) * (lm - m)
    return s + 0.3 * dm + 0.1 * (l5 - s - dm)


def recal(x):
    return RECAL[0] + RECAL[1] * np.asarray(x)


def rule(b, per_season):
    wins = sum(1 for v in per_season.values() if v < 0)
    ok = b["ci95"][1] < 0 and wins > len(per_season) / 2
    worse = b["ci95"][0] > 0
    return {"better_in_seasons": f"{wins}/{len(per_season)}",
            "verdict": "better" if ok else "worse" if worse else "not better (tie)"}


def score(df, new, old, target, season_col="season", key="PLAYER_ID"):
    df = df.reset_index(drop=True)
    en, eo = np.abs(df[new] - df[target]).to_numpy(), np.abs(df[old] - df[target]).to_numpy()
    b = tm.boot(df, en, eo, key=key)
    per = {s: float((en[g] - eo[g]).mean()) for s, g in df.groupby(season_col).indices.items()}
    return {"n": len(df), "players": int(df[key].nunique()), "mae_old": float(eo.mean()), "mae_new": float(en.mean()),
            "diff": b, "per_season": {k: round(v, 3) for k, v in per.items()}, **rule(b, per)}


# ---------------------------------------------------------------- shared per-season structures
def team_tables(pg_s, tg_s):
    """Team-game table with opponent id and fantasy points / points allowed."""
    t = tg_s[["GAME_ID", "TEAM_ID", "TEAM_ABBREVIATION", "GAME_DATE", "PTS"]].copy()
    o = t.rename(columns={"TEAM_ID": "OPP_ID", "PTS": "OPP_PTS"})[["GAME_ID", "OPP_ID", "OPP_PTS"]]
    t = t.merge(o, on="GAME_ID")
    t = t[t.TEAM_ID != t.OPP_ID]
    scored = pg_s.groupby(["GAME_ID", "TEAM_ID"]).FPTS.sum().rename("OPP_FPTS").reset_index()
    t = t.merge(scored.rename(columns={"TEAM_ID": "OPP_ID"}), on=["GAME_ID", "OPP_ID"], how="left")
    return t.sort_values("GAME_DATE").reset_index(drop=True)   # OPP_FPTS / OPP_PTS = allowed by TEAM_ID


def absence_reason_lookup(rep_s):
    """(player, date) -> reason for Out rows."""
    out = rep_s[rep_s["Current Status"] == "Out"]
    return {(p, d): r for p, d, r in zip(out.PLAYER_ID, out.GAME_DATE, out.Reason)}


def absence_type(reasons):
    if not reasons:
        return "unknown"
    reason = Counter(reasons).most_common(1)[0][0]
    if bpv.absence_reason(reason) != "injury":
        return "non_injury"
    return "serious" if bpv.injury_type(reason) == "serious" else "other_injury"


def build(pg, tg, rep):
    """Return events (C1 descriptive) and checkpoint rows (C1 test, C4)."""
    events, rows = [], []
    for s in SEASONS:
        g_all = pg[s].sort_values("GAME_DATE")
        tt = team_tables(g_all, tg[s])
        sched = {t: sorted(d) for t, d in tt.groupby("TEAM_ID").GAME_DATE}
        opp_of = dict(zip(zip(tt.GAME_ID, tt.TEAM_ID), tt.OPP_ID))
        reasons = absence_reason_lookup(rep[rep.season == s])
        cps = bt.checkpoints(g_all, 28)
        # Per checkpoint: team strength to date (relative to league) and remaining opponents.
        cp_info = {}
        for c in cps:
            before, after = tt[tt.GAME_DATE < c], tt[tt.GAME_DATE >= c]
            fpa = before.groupby("TEAM_ID").OPP_FPTS.mean()
            pa = before.groupby("TEAM_ID").OPP_PTS.mean()
            rel_f, rel_p = fpa / fpa.mean() - 1, pa / pa.mean() - 1
            rem = after.groupby("TEAM_ID").size()
            rem_f = after.assign(x=after.OPP_ID.map(rel_f)).groupby("TEAM_ID").x.mean()
            rem_p = after.assign(x=after.OPP_ID.map(rel_p)).groupby("TEAM_ID").x.mean()
            played = before.groupby("TEAM_ID").size()
            cp_info[c] = (rel_f.to_dict(), rel_p.to_dict(), rem.to_dict(), float(rem.mean()), rem_f.to_dict(),
                          rem_p.to_dict(), played.to_dict())
        for pid, g in g_all.groupby("PLAYER_ID"):
            dates = g.GAME_DATE.tolist()
            fp, mins = g.FPTS.to_numpy(float), g.MIN.to_numpy(float)
            teams, gids = g.TEAM_ID.tolist(), g.GAME_ID.tolist()
            opps = [opp_of.get((gi, t)) for gi, t in zip(gids, teams)]
            gaps = [0] + [min(bpv._count_between(sched[teams[k - 1]], dates[k - 1], dates[k]),
                              bpv._count_between(sched[teams[k]], dates[k - 1], dates[k]))
                          for k in range(1, len(dates))]
            returns = [k for k in range(1, len(dates)) if gaps[k] >= GAP]
            ret_type = {}
            for r in returns:
                team = teams[r - 1]
                missed = [d for d in sched[team] if dates[r - 1] < d < dates[r]]
                ret_type[r] = absence_type([reasons[(pid, d)] for d in missed if (pid, d) in reasons])
                if r >= 10 and mins[:r].mean() >= 20:
                    nxt = [k for k in returns if k > r]
                    end = nxt[0] if nxt else len(dates)
                    ev = {"season": s, "PLAYER_ID": pid, "gap": gaps[r], "type": ret_type[r],
                          "pre_min": mins[:r].mean(), "pre_fp": fp[:r].mean(),
                          "pre10_min": mins[r - 10:r].mean(), "pre10_fp": fp[r - 10:r].mean()}
                    for lab, a, b in [("g1_3", 0, 3), ("g4_10", 3, 10), ("g11p", 10, 10 ** 6)]:
                        sl = slice(r + a, min(r + b, end))
                        n = max(0, min(r + b, end) - (r + a))
                        ev[f"{lab}_n"] = n
                        ev[f"{lab}_min"] = mins[sl].mean() if n else np.nan
                        ev[f"{lab}_fp"] = fp[sl].mean() if n else np.nan
                    events.append(ev)
            for c in cps:
                i = bisect_left(dates, c)
                if i < 10:
                    continue
                rel_f, rel_p, rem, avg_rem, rem_f, rem_p, played = cp_info[c]
                team = teams[i - 1]
                past_f = np.nanmean([rel_f.get(o, np.nan) for o in opps[:i]])
                past_p = np.nanmean([rel_p.get(o, np.nan) for o in opps[:i]])
                row = {"season": s, "checkpoint": c, "PLAYER_ID": pid, "n": i, "mpg_S": mins[:i].mean(),
                       "cur_raw": raw_pred(fp[:i], mins[:i]), "n_after": len(dates) - i,
                       "A_ros": fp[i:].mean() if i < len(dates) else np.nan, "sum_after": fp[i:].sum(),
                       "share": min(i / max(played.get(team, i), 1), 1.0), "rem": rem.get(team, 0), "avg_rem": avg_rem,
                       "x_f": rem_f.get(team, np.nan) - past_f, "x_p": rem_p.get(team, np.nan) - past_p,
                       "rem_f": rem_f.get(team, np.nan), "rem_p": rem_p.get(team, np.nan)}
                prior = [r for r in returns if r < i]
                if prior:
                    r = prior[-1]
                    row.update({"post": i - r, "ret_type": ret_type[r], "pre_n": r,
                                "pre_mpg": mins[:r].mean() if r else np.nan,
                                "pre_raw": raw_pred(fp[:r], mins[:r]) if r >= 5 else np.nan,
                                # current formula with the first 3 games after return left out
                                "skip3_raw": raw_pred(np.r_[fp[:r], fp[r + 3:i]], np.r_[mins[:r], mins[r + 3:i]])
                                if i - r > 3 else raw_pred(fp[:r], mins[:r]) if r >= 5 else np.nan})
                rows.append(row)
    return pd.DataFrame(events), pd.DataFrame(rows)


# ---------------------------------------------------------------- C1
def c1(events, cp):
    res = {"n_events": len(events), "events_by_type": events.type.value_counts().to_dict(),
           "median_gap": float(events.gap.median())}

    def traj(e):
        out = {"n": len(e)}
        for lab in ["g1_3", "g4_10", "g11p"]:
            ok = e[e[f"{lab}_n"] > 0]
            out[lab] = {"n": len(ok), "min_ratio": round(float(ok[f"{lab}_min"].sum() / ok.pre_min.sum()), 3),
                        "fp_ratio": round(float(ok[f"{lab}_fp"].sum() / ok.pre_fp.sum()), 3),
                        "min_diff": round(float((ok[f"{lab}_min"] - ok.pre_min).mean()), 2),
                        "fp_diff": round(float((ok[f"{lab}_fp"] - ok.pre_fp).mean()), 2),
                        "fp_ratio_vs_last10": round(float(ok[f"{lab}_fp"].sum() / ok.pre10_fp.sum()), 3)}
        return out
    res["trajectory_all"] = traj(events)
    res["trajectory_by_type"] = {t: traj(e) for t, e in events.groupby("type")}
    res["trajectory_gap_20plus"] = traj(events[events.gap >= 20])

    d = cp[(cp.n_after >= 10) & (cp.mpg_S >= 12)].copy()
    d["cur"] = recal(d.cur_raw)
    f = d[d.post.notna() & (d.post <= 10) & (d.pre_n >= 10) & (d.pre_mpg >= 20) & d.pre_raw.notna()].copy()
    f["grp"] = np.where(f.post <= 3, "1-3", "4-10")
    f["ser"] = np.where(f.ret_type == "serious", "serious", "other")
    res["checkpoint_rows_all"] = len(d)
    res["flagged_rows"] = {"n": len(f), "players": int(f.PLAYER_ID.nunique()), "by_group": f.grp.value_counts().to_dict(),
                           "by_type": f.ret_type.value_counts().to_dict()}
    res["mean_residual_current"] = {"all_rows": round(float((d.A_ros - d.cur).mean()), 3),
                                    "flagged": round(float((f.A_ros - f.cur).mean()), 3),
                                    "flagged_by_group": (f.A_ros - f.cur).groupby(f.grp).mean().round(3).to_dict(),
                                    "flagged_pre_minus_cur_raw": round(float((f.pre_raw - f.cur_raw).mean()), 3)}
    f["pre_only"] = recal(f.pre_raw)
    f["skip3"] = recal(f.skip3_raw)
    # Fitted blend toward the pre-absence projection, leave one season out.
    for name, cols in [("blend_by_post", ["grp"]), ("blend_by_post_type", ["grp", "ser"])]:
        out, betas = [], {}
        for s in SEASONS:
            tr, te = f[f.season != s], f[f.season == s].copy()
            if te.empty:
                continue
            key_tr, key_te = tr[cols].agg("|".join, axis=1), te[cols].agg("|".join, axis=1)
            x_tr = RECAL[1] * (tr.pre_raw - tr.cur_raw)
            y_tr = tr.A_ros - tr.cur
            beta = {k: float((x_tr[key_tr == k] * y_tr[key_tr == k]).sum() / (x_tr[key_tr == k] ** 2).sum())
                    for k in key_tr.unique()}
            betas[s] = {k: round(v, 3) for k, v in beta.items()}
            te[name] = te.cur + key_te.map(beta).fillna(0) * RECAL[1] * (te.pre_raw - te.cur_raw)
            out.append(te)
        f = f.merge(pd.concat(out)[[name]], left_index=True, right_index=True, how="left")
        res[f"{name}_betas_by_heldout_season"] = betas
    res["tests"] = {v: score(f, v, "cur", "A_ros") for v in ["pre_only", "skip3", "blend_by_post", "blend_by_post_type"]}
    ser = f[f.ret_type == "serious"]
    res["tests_serious_only"] = {v: {k: x for k, x in score(ser, v, "cur", "A_ros").items() if k != "per_season"}
                                 for v in ["pre_only", "blend_by_post"]} if len(ser) > 30 else "too few"
    return res


# ---------------------------------------------------------------- C2
def c2(pg, tg):
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    rows = []
    for t in SEASONS:
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        hp = hist[(hist.season == prev) & (hist.mpg >= 20) & (hist.played >= 20)].set_index("PLAYER_ID")
        stars = set(hp.fpts_pg.sort_values(ascending=False).index[:50])
        actual = hist[(hist.season == t) & hist.PLAYER_ID.isin(hp.index)].set_index("PLAYER_ID").availability
        p_league, _ = rb.league_before(hist, t)
        p_hat = bpv.predict_availability(hist, bt.SEASONS, prev, 0.5, 123, p_league).reindex(actual.index)
        for pid in actual.index:
            rows.append({"season": t, "PLAYER_ID": pid, "star": pid in stars, "avail": actual[pid],
                         "p_hat": p_hat[pid], "post": t >= "2023-24"})
    d = pd.DataFrame(rows)
    d["resid"] = d.avail - d.p_hat
    by = d.groupby(["season", "star"]).agg(avail=("avail", "mean"), resid=("resid", "mean"), n=("avail", "size"))
    res = {"by_season": {f"{s}|{'star' if st else 'other'}": {k: round(float(v), 3) for k, v in r.items()}
                         for (s, st), r in by.iterrows()}}

    def did(x, col):
        m = x.groupby(["post", "star"])[col].mean()
        return (m[(True, True)] - m[(True, False)]) - (m[(False, True)] - m[(False, False)])
    rng = np.random.default_rng(5)
    groups = d.groupby("PLAYER_ID").indices
    ids = list(groups)
    for col in ["avail", "resid"]:
        point = float(did(d, col))
        boots = []
        for _ in range(500):
            idx = np.concatenate([groups[ids[i]] for i in rng.choice(len(ids), len(ids))])
            boots.append(did(d.iloc[idx], col))
        res[f"diff_in_diff_{col}"] = {"point": round(point, 4), "ci95": [round(float(x), 4) for x in np.percentile(boots, [2.5, 97.5])]}
    # Prediction test for stars: add the star residual from post-policy seasons before the target.
    st = d[d.star].copy()
    out = []
    for t, fit in [("2024-25", ["2023-24"]), ("2025-26", ["2023-24"])]:
        te = st[st.season == t].copy()
        delta = float(st[st.season.isin(fit)].resid.mean())
        te["new"] = (te.p_hat + delta).clip(0, 1)
        te["new_expanding"] = (te.p_hat + float(st[(st.season >= "2023-24") & (st.season < t)].resid.mean())).clip(0, 1)
        te["delta"] = delta
        out.append(te)
    t = pd.concat(out)
    res["star_adjustment_2023_24"] = round(float(st[st.season == "2023-24"].resid.mean()), 4)
    res["star_resid_pre_policy"] = round(float(st[~st.post].resid.mean()), 4)
    res["test_fit_2023_24"] = score(t, "new", "p_hat", "avail")
    res["test_fit_expanding"] = score(t, "new_expanding", "p_hat", "avail")
    return res


# ---------------------------------------------------------------- C3
def c3(pg, tg, rep):
    slots = []
    for s in SEASONS:
        g_all = pg[s].sort_values("GAME_DATE")
        tgs = tg[s]
        tdates = {t: sorted(x) for t, x in tgs.groupby("TEAM_ID").GAME_DATE}
        tset = {t: set(x) for t, x in tdates.items()}
        fp_by = dict(zip(zip(g_all.PLAYER_ID, g_all.GAME_DATE), g_all.FPTS))
        min_by = dict(zip(zip(g_all.PLAYER_ID, g_all.GAME_DATE), g_all.MIN))
        ages = nba_data.player_ages(s).set_index("PLAYER_ID").AGE
        rs = rep[rep.season == s]
        rdates = sorted(rs.REPORT_DATE.unique())
        first = dt.date.fromisoformat(g_all.GAME_DATE.min())
        monday = first + dt.timedelta(days=(7 - first.weekday()) % 7 + 21)
        last = dt.date.fromisoformat(g_all.GAME_DATE.max())
        while monday + dt.timedelta(days=6) <= last:
            ws, we = monday.isoformat(), (monday + dt.timedelta(days=7)).isoformat()
            prev3 = [(monday - dt.timedelta(days=k)).isoformat() for k in (1, 2, 3)]
            j = bisect_left(rdates, ws) - 1
            latest = rs[rs.REPORT_DATE == rdates[j]] if j >= 0 else rs.iloc[0:0]
            status = {}
            for pid, stt, cat, ser in zip(latest.PLAYER_ID, latest["Current Status"], latest.category, latest.serious):
                status[pid] = "out_serious" if (stt == "Out" and ser) else f"{stt.lower()}_{cat}" if stt == "Out" else stt.lower()
            before = g_all[g_all.GAME_DATE < ws]
            team_before = tgs[tgs.GAME_DATE < ws].groupby("TEAM_ID").size()
            st = before.groupby("PLAYER_ID").agg(fp=("FPTS", "mean"), n=("FPTS", "size"), mpg=("MIN", "mean"),
                                                 team=("TEAM_ID", "last"))
            for pid, r in st[(st.mpg >= 20) & (st.n >= 10)].iterrows():
                wk = [d for d in tdates[r.team] if ws <= d < we]
                if not wk:
                    continue
                team_prev3 = sum(d in tset[r.team] for d in prev3)
                m3 = sum(min_by.get((pid, d), 0.0) for d in prev3)
                p3 = "team_idle" if team_prev3 == 0 else "sat" if m3 == 0 else "light" if m3 <= 36 else "heavy"
                for d in wk:
                    b2b = (dt.date.fromisoformat(d) - dt.timedelta(days=1)).isoformat() in tset[r.team]
                    slots.append({"season": s, "week": ws, "PLAYER_ID": pid, "fp": r.fp,
                                  "share": min(r.n / team_before.get(r.team, r.n), 1.0),
                                  "status": status.get(pid, "not_listed"), "b2b": b2b, "old": ages.get(pid, 0) >= 30,
                                  "star": r.fp >= 40, "prev3": p3, "actual_g": fp_by.get((pid, d), 0.0),
                                  "played": (pid, d) in fp_by})
            monday += dt.timedelta(days=7)
    sl = pd.DataFrame(slots)
    sl["grp"] = (np.where(sl.b2b, "b2b", "rest") + np.where(sl.old, "_30+", "_u30") + np.where(sl.star, "_star", ""))
    sl["grp2"] = np.where(sl.b2b, "b2b", "rest") + np.where(sl.old, "_30+", "_u30")
    res = {"n_slots": len(sl), "b2b_share_of_games": round(float(sl.b2b.mean()), 3),
           "play_rate_by_group_all_seasons": sl.groupby("grp").played.agg(["mean", "size"]).round(3).to_dict("index"),
           "fp_when_played_ratio_by_group": (sl[sl.played].groupby("grp").actual_g.sum() /
                                             sl[sl.played].groupby("grp").fp.sum()).round(3).to_dict()}
    wk_key = ["season", "week", "PLAYER_ID"]
    scored = []
    fits = {}
    for s in SEASONS:
        tr, te = sl[sl.season != s].copy(), sl[sl.season == s].copy()
        sf = tr.groupby("status").actual_g.sum() / (tr.fp * tr.share).groupby(tr.status).sum()
        for x in (tr, te):
            x["unit"] = x.fp * x.share * x.status.map(sf).fillna(1.0)
        r1 = tr.groupby("grp").actual_g.sum() / tr.groupby("grp").unit.sum()
        r2 = tr.groupby("grp2").actual_g.sum() / tr.groupby("grp2").unit.sum()
        for x in (tr, te):
            x["v1"] = x.unit * x.grp.map(r1).fillna(1.0)
            x["v1b"] = x.unit * x.grp2.map(r2).fillna(1.0)
        wtr = tr.groupby(wk_key).agg(actual=("actual_g", "sum"), v1=("v1", "sum"), prev3=("prev3", "first"))
        m = wtr.groupby("prev3").actual.sum() / wtr.groupby("prev3").v1.sum()
        w = te.groupby(wk_key).agg(actual=("actual_g", "sum"), base=("unit", "sum"), v1=("v1", "sum"),
                                   v1b=("v1b", "sum"), prev3=("prev3", "first"), b2b=("b2b", "sum"),
                                   status=("status", "first")).reset_index()
        w["v2"] = w.v1 * w.prev3.map(m).fillna(1.0)
        fits[s] = {"b2b_ratio": r1.round(3).to_dict(), "prev3_mult": m.round(3).to_dict()}
        scored.append(w)
    w = pd.concat(scored, ignore_index=True)
    res["fit_heldout_2025_26"] = fits["2025-26"]
    # Sanity: is "sat" (team played in the 3 days before the week, player did not) just the injury status again?
    w["listed"] = np.where(w.status == "not_listed", "not_listed", "listed")
    res["prev3_sanity"] = {f"{a}|{b}": {"weeks": int(len(g)), "actual_over_base": round(float(g.actual.sum() / g.base.sum()), 3),
                                        "v2_minus_base_mae": round(float((np.abs(g.v2 - g.actual) - np.abs(g.base - g.actual)).mean()), 2)}
                           for (a, b), g in w.groupby(["prev3", "listed"])}
    ok = w[w.prev3 != "sat"].reset_index(drop=True)
    res["v2_excluding_sat_weeks"] = score(ok, "v2", "base", "actual")
    res["tests"] = {v: score(w, v, "base", "actual") for v in ["v1b", "v1", "v2"]}
    hb = w[w.b2b > 0].reset_index(drop=True)
    res["weeks_with_b2b_only_v1"] = {k: x for k, x in score(hb, "v1", "base", "actual").items()}
    res["test_2025_26_only_v1"] = {k: x for k, x in score(w[w.season == "2025-26"], "v1", "base", "actual").items()
                                   if k != "per_season"}
    return res


# ---------------------------------------------------------------- C4
def c4(cp):
    d = cp[(cp.n_after >= 10) & (cp.mpg_S >= 12)].dropna(subset=["x_f", "x_p"]).copy()
    d["cur"] = recal(d.cur_raw)
    d["rem_dev"] = d.rem - d.avg_rem
    res = {"n": len(d), "players": int(d.PLAYER_ID.nunique()),
           "sd_x_fpts_allowed": round(float(d.x_f.std()), 4), "sd_rem_fpts_allowed": round(float(d.rem_f.std()), 4)}
    variants = {"fpa_rem_minus_past": ["x_f"], "pa_rem_minus_past": ["x_p"], "fpa_rem_only": ["rem_f"],
                "fpa_plus_rem_games": ["x_f", "rem_dev"]}
    coefs = {}
    for name, cols in variants.items():
        out, cf = [], {}
        for s in SEASONS:
            tr, te = d[d.season != s], d[d.season == s].copy()
            X = np.column_stack([tr.cur * tr[c] if c != "rem_dev" else tr[c] for c in cols])
            b, *_ = np.linalg.lstsq(X, (tr.A_ros - tr.cur).to_numpy(), rcond=None)
            cf[s] = [round(float(x), 4) for x in b]
            Xt = np.column_stack([te.cur * te[c] if c != "rem_dev" else te[c] for c in cols])
            te[name] = te.cur + Xt @ b
            out.append(te[[name]])
        d = d.join(pd.concat(out))
        coefs[name] = cf
    res["coefs_by_heldout_season"] = coefs
    res["tests"] = {v: score(d, v, "cur", "A_ros") for v in variants}
    # Totals: exact remaining team games vs the league-average remaining at that date.
    t = cp[(cp.mpg_S >= 20)].copy()
    t["cur"] = recal(t.cur_raw)
    t["tot_exact"] = t.cur * t.share * t.rem
    t["tot_avg"] = t.cur * t.share * t.avg_rem
    res["totals"] = score(t, "tot_exact", "tot_avg", "sum_after")
    res["totals"]["mean_abs_rem_minus_avg"] = round(float((t.rem - t.avg_rem).abs().mean()), 2)
    res["totals"]["mean_actual_total"] = round(float(t.sum_after.mean()), 1)
    return res


def main():
    pg, tg = bt.load()
    rep, _ = ti.load_reports(pg)
    events, cp = build(pg, tg, rep)
    print("built", len(events), len(cp), flush=True)
    if os.environ.get("ONLY_C3"):
        print("C3", json.dumps(c3(pg, tg, rep), default=float))
        return
    res = {"C1": c1(events, cp)}
    print("C1", json.dumps(res["C1"], default=float), flush=True)
    res["C4"] = c4(cp)
    print("C4", json.dumps(res["C4"], default=float), flush=True)
    res["C2"] = c2(pg, tg)
    print("C2", json.dumps(res["C2"], default=float), flush=True)
    res["C3"] = c3(pg, tg, rep)
    print("C3", json.dumps(res["C3"], default=float), flush=True)
    if OUT:
        with open(OUT, "w") as f:
            json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
