"""Production after returning from an injury absence (rules fixed beforehand in docs/prereg-injury-return.md).

Test A: in-season absences of 5+ team games by regulars, scored at the return and 5 games after it.
Test B: players back from a whole missed season.
Writes analysis/injury_return.json.

    python -m analysis.injury_return
"""
import json
import os
import warnings
from bisect import bisect_left, bisect_right

import numpy as np
import pandas as pd

import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "injury_return.json")
SEASONS = [nba_data.season_string(y) for y in range(2009, 2026)]
REPORT_SEASONS = [nba_data.season_string(y) for y in range(2021, 2026)]
MIN_GAP, MIN_BEFORE, MIN_MPG, MIN_LEFT, MIN_AFTER = 5, 10, 20, 10, 3
LENGTH_BUCKETS = [(5, 9, "5-9"), (10, 19, "10-19"), (20, 39, "20-39"), (40, 999, "40+")]
STAR = 40
NO_OVERRIDES = {"injuries": {}, "role_changes": {}}
BOOT = 2000


def length_bucket(gap):
    return next(name for lo, hi, name in LENGTH_BUCKETS if lo <= gap <= hi)


def efg(g):
    fga = g["FGA"].sum()
    return (g["FGM"].sum() + 0.5 * g["FG3M"].sum()) / fga if fga else np.nan


def bpv_production(g, prev, age, prior_efg, league_efg):
    """ratings.build's in-season production for one player's games so far (no preseason prior)."""
    production, _ = ratings._production(g, "in-season", NO_OVERRIDES)
    n = len(g)
    if prev is not None:
        prior = prev["fpts_pg"] + (ratings.AGE_CURVE[bpv.age_bucket(age)] if prev["mpg"] >= ratings.AGE_MIN_MPG
                                   and age is not None and not pd.isna(age) else 0.0)
        production = bpv.shrink(production, n, prior, ratings.PRIOR_SEASON_K)
    if n >= ratings.RECALIBRATION_MIN_GAMES:
        production = ratings.RECALIBRATION[0] + ratings.RECALIBRATION[1] * production
        fga = g["FGA"].sum()
        if fga > 0:
            production += ratings.SHOOTING_REGRESSION * (efg(g) - prior_efg.get(g["PLAYER_ID"].iloc[0], league_efg)) * fga / n
    return production


def report_types(season):
    """(normalized name) -> list of (date, injury type) for every Out-with-injury listing that season."""
    try:
        rep = nba_data.injury_reports(season)
    except Exception:
        return {}
    rep = rep[(rep["Current Status"] == "Out")]
    rep = rep[rep["Reason"].map(bpv.absence_reason) == "injury"]
    out = {}
    for d, n, r in zip(rep["REPORT_DATE"], rep["Player Name"], rep["Reason"]):
        out.setdefault(ratings.normalize_name(bpv.report_player_name(n)), []).append((d, bpv.injury_type(r)))
    return out


def season_events(season, pg, tg, pg_prev, ages_prev):
    games = pg[season]
    team_dates = {t: sorted(d) for t, d in tg[season].groupby("TEAM_ID")["GAME_DATE"]}
    prev = None
    if pg_prev is not None:
        p = pg_prev.groupby("PLAYER_ID").agg(played=("FPTS", "size"), fpts_pg=("FPTS", "mean"), mpg=("MIN", "mean"))
        prev = p[p["played"] >= 20]
        shots = pg_prev.groupby("PLAYER_ID")[["FGM", "FG3M", "FGA"]].sum()
        shots = shots[shots["FGA"] >= ratings.SHOOTING_PRIOR_MIN_FGA]
        prior_efg = ((shots["FGM"] + 0.5 * shots["FG3M"]) / shots["FGA"]).to_dict()
    else:
        prior_efg = {}
    types = report_types(season) if season in REPORT_SEASONS else None
    rows = []
    for pid, g in games.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE").reset_index(drop=True)
        dates, teams = g["GAME_DATE"].tolist(), g["TEAM_ID"].tolist()
        for i in range(len(g) - 1):
            d1, d2 = dates[i], dates[i + 1]
            if teams[i] != teams[i + 1]:
                continue                                    # traded during the gap: can't tell
            sched = team_dates[teams[i]]
            gap = max(0, bisect_left(sched, d2) - bisect_right(sched, d1))
            if gap < MIN_GAP:
                continue
            before = g.iloc[: i + 1]
            if len(before) < MIN_BEFORE or before["MIN"].mean() < MIN_MPG:
                continue
            left = len(sched) - bisect_left(sched, d2)
            if left < MIN_LEFT:
                continue
            after = g.iloc[i + 1:]
            pv = prev.loc[pid] if prev is not None and pid in prev.index else None
            age = ages_prev.get(pid) if ages_prev is not None else None
            sofar = games[games["GAME_DATE"] <= d1]
            league_efg = efg(sofar)
            kind = None
            if types is not None:
                listed = [k for d, k in types.get(ratings.normalize_name(g["PLAYER_NAME"].iloc[-1]), []) if d1 < d < d2]
                kind = ("serious" if "serious" in listed else "other") if listed else "unlisted"
            age_now = (age + 1) if age is not None and not pd.isna(age) else None
            for checkpoint in (0, 5):
                rest = after.iloc[checkpoint:]
                if len(rest) < MIN_AFTER:
                    continue
                known = pd.concat([before, after.iloc[:checkpoint]])
                rows.append({
                    "season": season, "player": int(pid), "name": g["PLAYER_NAME"].iloc[-1], "checkpoint": checkpoint,
                    "gap": gap, "bucket": length_bucket(gap), "old": bool(age_now is not None and age_now >= 30),
                    "type": kind, "baseline": bpv_production(known, pv, age, prior_efg, league_efg),
                    "pre_fpg": before["FPTS"].mean(), "pre_mpg": before["MIN"].mean(),
                    "actual": rest["FPTS"].mean(), "post_mpg": rest["MIN"].mean(), "w": len(rest),
                })
    return rows


def wmae(pred, actual, w):
    return float(np.sum(w * np.abs(pred - actual)) / np.sum(w))


def loso(df, keys):
    """Leave-one-season-out multiplier per group (games-weighted actual / baseline)."""
    pred = np.empty(len(df))
    for s in df["season"].unique():
        train, test = df[df["season"] != s], df["season"] == s
        g = train.assign(a=train["w"] * train["actual"], b=train["w"] * train["baseline"]).groupby(keys)[["a", "b"]].sum()
        ratio = (g["a"] / g["b"]).to_dict()
        overall = train["w"].mul(train["actual"]).sum() / train["w"].mul(train["baseline"]).sum()
        k = df.loc[test, keys].apply(tuple, axis=1) if len(keys) > 1 else df.loc[test, keys[0]]
        pred[test.to_numpy()] = df.loc[test, "baseline"].to_numpy() * k.map(lambda x: ratio.get(x, overall)).to_numpy()
    return pred


def compare(df, pred_new, pred_old, seed=7):
    """Adoption-rule numbers for pred_new vs pred_old (lower error = better)."""
    a, w = df["actual"].to_numpy(), df["w"].to_numpy(float)
    e_new, e_old = w * np.abs(pred_new - a), w * np.abs(pred_old - a)
    out = {"events": int(len(df)), "players": int(df["player"].nunique()),
           "mae_new": wmae(pred_new, a, w), "mae_old": wmae(pred_old, a, w)}
    out["diff"] = out["mae_new"] - out["mae_old"]
    # Bootstrap clustered by player.
    rng = np.random.default_rng(seed)
    players = df["player"].to_numpy()
    uniq = np.unique(players)
    idx = {p: np.flatnonzero(players == p) for p in uniq}
    diffs = []
    for _ in range(BOOT):
        take = np.concatenate([idx[p] for p in rng.choice(uniq, len(uniq))])
        diffs.append(e_new[take].sum() / w[take].sum() - e_old[take].sum() / w[take].sum())
    out["ci"] = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    seasons = {}
    for s, g in df.groupby("season"):
        m = (df["season"] == s).to_numpy()
        seasons[s] = round(wmae(pred_new[m], a[m], w[m]) - wmae(pred_old[m], a[m], w[m]), 3)
    out["by_season"] = seasons
    out["seasons_better"] = f"{sum(v < 0 for v in seasons.values())} of {len(seasons)}"
    star = (df["baseline"] >= STAR).to_numpy()
    out["stars"] = {"events": int(star.sum()),
                    "diff": wmae(pred_new[star], a[star], w[star]) - wmae(pred_old[star], a[star], w[star]) if star.any() else None}
    better_share = sum(v < 0 for v in seasons.values()) / max(len(seasons), 1)
    out["passes"] = bool(out["ci"][1] < 0 and better_share >= 0.6 and (out["stars"]["diff"] is None or out["stars"]["diff"] <= 0))
    return out


def describe(df):
    g = df.groupby("bucket", sort=False)
    return {b: {"events": int(len(x)), "actual_over_baseline": round(float((x.w * x.actual).sum() / (x.w * x.baseline).sum()), 3),
                "actual_over_pre": round(float((x.w * x.actual).sum() / (x.w * x.pre_fpg).sum()), 3),
                "minutes_after_over_before": round(float((x.w * x.post_mpg).sum() / (x.w * x.pre_mpg).sum()), 3)}
            for b, x in g}


def test_a(pg, tg, ages):
    rows = []
    for i, s in enumerate(SEASONS):
        prev = SEASONS[i - 1] if i else None
        rows += season_events(s, pg, tg, pg.get(prev), ages.get(prev))
    df = pd.DataFrame(rows)
    order = [b for _, _, b in LENGTH_BUCKETS]
    df["bucket"] = pd.Categorical(df["bucket"], order, ordered=True)
    out = {}
    for cp, d in df.groupby("checkpoint"):
        d = d.reset_index(drop=True)
        base = d["baseline"].to_numpy()
        c1 = loso(d, ["bucket"])
        res = {"describe": describe(d), "length": compare(d, c1, base),
               "length_age_vs_length": compare(d, loso(d, ["bucket", "old"]), c1)}
        rep = d[d["type"].notna()].reset_index(drop=True)
        if len(rep):
            r1 = loso(rep, ["bucket"])
            res["type_vs_length (2021-22 on)"] = compare(rep, loso(rep, ["bucket", "type"]), r1)
            res["by_type (2021-22 on)"] = {t: {"events": int(len(x)), "actual_over_baseline":
                                               round(float((x.w * x.actual).sum() / (x.w * x.baseline).sum()), 3)}
                                           for t, x in rep.groupby("type")}
        out[f"checkpoint_{cp}_games_after_return"] = res
    return out, df


def test_b(pg, ages):
    rows = []
    for i in range(2, len(SEASONS)):
        s2, s1, s = SEASONS[i - 2], SEASONS[i - 1], SEASONS[i]
        a2 = pg[s2].groupby("PLAYER_ID").agg(n=("FPTS", "size"), fpg=("FPTS", "mean"), mpg=("MIN", "mean"),
                                             name=("PLAYER_NAME", "last"))
        a2 = a2[(a2["n"] >= 20) & (a2["mpg"] >= ratings.AGE_MIN_MPG)]
        missed = set(a2.index) - set(pg[s1]["PLAYER_ID"])
        now = pg[s].groupby("PLAYER_ID").agg(n=("FPTS", "size"), fpg=("FPTS", "mean"))
        age2 = ages.get(s2)
        for pid in missed:
            if pid not in now.index or now.loc[pid, "n"] < 10:
                continue
            age = age2.get(pid) if age2 is not None else None
            adj = ratings.AGE_CURVE[bpv.age_bucket(age + 1)] if age is not None and not pd.isna(age) else 0.0
            rows.append({"season": s, "player": int(pid), "name": a2.loc[pid, "name"], "baseline": a2.loc[pid, "fpg"] + adj,
                         "pre_fpg": a2.loc[pid, "fpg"], "actual": now.loc[pid, "fpg"], "w": int(now.loc[pid, "n"])})
    df = pd.DataFrame(rows)
    df["all"] = "all"
    res = compare(df, loso(df, ["all"]), df["baseline"].to_numpy())
    res["actual_over_baseline"] = round(float((df.w * df.actual).sum() / (df.w * df.baseline).sum()), 3)
    res["examples"] = df.sort_values("pre_fpg", ascending=False).head(15)[["season", "name", "pre_fpg", "baseline", "actual", "w"]] \
        .round(1).to_dict(orient="records")
    return res


def main():
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in SEASONS}
    tg = {s: nba_data.team_game_logs(s) for s in SEASONS}
    ages = {}
    for s in SEASONS:
        try:
            ages[s] = nba_data.player_ages(s).set_index("PLAYER_ID")["AGE"]
        except Exception:
            ages[s] = None
    a, events = test_a(pg, tg, ages)
    b = test_b(pg, ages)
    out = {"rules": "docs/prereg-injury-return.md", "test_a": a, "test_b_whole_season": b}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
