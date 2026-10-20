"""Rest-of-season share played after an Out listing (rules fixed beforehand in docs/prereg-report-share.md).

C0 is what ratings.build does now (share x normal availability, which counts ordinary absences twice); C1 is the share
alone; C2 splits it by games left; C3 is normal availability after the typical streak. Writes analysis/report_share.json.

    python -m analysis.report_share
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_share.json")
SEASONS = [nba_data.season_string(y) for y in range(2021, 2026)]
MIN_LEFT, MIN_GAMES, MIN_MPG, STAR = 10, 5, 20, 40
LEFT_BUCKETS = [(10, 40, "10-40"), (41, 60, "41-60"), (61, 99, "61+")]
BOOT = 2000


def history_availability(target):
    """player id -> BPV's availability estimate before `target` (seasons before it only)."""
    y = nba_data.season_start_year(target)
    window = [nba_data.season_string(x) for x in range(y - ratings.HISTORY_SEASONS, y)]
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in window}
    tg = {s: nba_data.team_game_logs(s) for s in window}
    hist = bpv.availability_history(window, pg, tg, nba_data.draft_history())
    league_p, _ = bpv.league_availability(hist)
    avail = bpv.predict_availability(hist, window, window[-1], ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K, league_p)
    return avail.to_dict(), league_p


def spells(season):
    pg, tg = bpv.add_fpts(nba_data.player_game_logs(season)), nba_data.team_game_logs(season)
    rep = nba_data.injury_reports(season)
    rep = rep[(rep["Current Status"] == "Out") & (rep["Reason"].map(bpv.absence_reason) == "injury")]
    team_dates = {t: sorted(d) for t, d in tg.groupby("TEAM_ABBREVIATION")["GAME_DATE"]}
    pg = pg.assign(key=pg["PLAYER_NAME"].map(ratings.normalize_name))
    by_player = {k: g.sort_values("GAME_DATE") for k, g in pg.groupby("key")}
    avail, league_p = history_availability(season)
    rows, seen = [], set()
    for d, n, reason in zip(rep["REPORT_DATE"], rep["Player Name"], rep["Reason"]):
        g = by_player.get(ratings.normalize_name(bpv.report_player_name(n)))
        if g is None:
            continue
        before = g[g["GAME_DATE"] < d]
        if len(before) < MIN_GAMES or before["MIN"].mean() < MIN_MPG:
            continue
        spell = (g["PLAYER_ID"].iloc[0], before["GAME_DATE"].iloc[-1])
        if spell in seen:
            continue
        seen.add(spell)
        team = before["TEAM_ABBREVIATION"].iloc[-1]
        left = [x for x in team_dates[team] if x >= d]
        if len(left) < MIN_LEFT:
            continue
        on_team = g[(g["GAME_DATE"] >= d) & (g["TEAM_ABBREVIATION"] == team)]
        played_dates = set(on_team["GAME_DATE"])
        streak = next((k for k, x in enumerate(left) if x in played_dates), len(left))
        pid = int(g["PLAYER_ID"].iloc[0])
        rows.append({"season": season, "player": pid, "type": bpv.injury_type(reason), "left": len(left),
                     "bucket": next(b for lo, hi, b in LEFT_BUCKETS if lo <= len(left) <= hi),
                     "availability": float(avail.get(pid, league_p)), "pre_fpg": float(before["FPTS"].mean()),
                     "streak": streak, "actual": min(len(on_team) / len(left), 1.0)})
    return rows


def loso_mean(df, keys, col):
    """Leave-one-season-out games-left-weighted mean of `col` by `keys` (falls back to all types pooled)."""
    out = np.empty(len(df))
    for s in df["season"].unique():
        train, test = df[df["season"] != s], (df["season"] == s).to_numpy()
        g = train.assign(x=train[col] * train["left"]).groupby(keys)[["x", "left"]].sum()
        means = (g["x"] / g["left"]).to_dict()
        pooled = (train[col] * train["left"]).sum() / train["left"].sum()
        k = df.loc[test, keys].apply(tuple, axis=1) if len(keys) > 1 else df.loc[test, keys[0]]
        out[test] = k.map(lambda x: means.get(x, pooled)).to_numpy()
    return out


def loso_streak_mean(df):
    """Leave-one-season-out plain mean streak by type (spells with 21+ games left, as on the injury page)."""
    out = np.empty(len(df))
    for s in df["season"].unique():
        train, test = df[(df["season"] != s) & (df["left"] > 20)], (df["season"] == s).to_numpy()
        means = train.groupby("type")["streak"].mean().to_dict()
        out[test] = df.loc[test, "type"].map(lambda t: means.get(t, train["streak"].mean())).to_numpy()
    return out


def compare(df, new, old, seed=7):
    a, w = df["actual"].to_numpy(), df["left"].to_numpy(float)
    e_new, e_old = w * np.abs(new - a), w * np.abs(old - a)
    res = {"spells": int(len(df)), "players": int(df["player"].nunique()),
           "mae_new": float(e_new.sum() / w.sum()), "mae_old": float(e_old.sum() / w.sum())}
    res["diff"] = res["mae_new"] - res["mae_old"]
    rng, players = np.random.default_rng(seed), df["player"].to_numpy()
    uniq = np.unique(players)
    idx = {p: np.flatnonzero(players == p) for p in uniq}
    diffs = []
    for _ in range(BOOT):
        t = np.concatenate([idx[p] for p in rng.choice(uniq, len(uniq))])
        diffs.append((e_new[t].sum() - e_old[t].sum()) / w[t].sum())
    res["ci"] = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    res["by_season"] = {s: round(float((e_new[m].sum() - e_old[m].sum()) / w[m].sum()), 4)
                        for s in df["season"].unique() for m in [(df["season"] == s).to_numpy()]}
    better = sum(v < 0 for v in res["by_season"].values())
    res["seasons_better"] = f"{better} of {len(res['by_season'])}"
    star = (df["pre_fpg"] >= STAR).to_numpy()
    res["stars"] = {"spells": int(star.sum()), "diff": float((e_new[star].sum() - e_old[star].sum()) / w[star].sum()) if star.any() else None}
    res["passes"] = bool(res["ci"][1] < 0 and better >= 3 and (res["stars"]["diff"] is None or res["stars"]["diff"] <= 0))
    res["mean_predicted_new"] = float((new * w).sum() / w.sum())
    res["mean_predicted_old"] = float((old * w).sum() / w.sum())
    res["mean_actual"] = float((a * w).sum() / w.sum())
    return res


def main():
    df = pd.DataFrame([r for s in SEASONS for r in spells(s)])
    c0 = df["type"].map(ratings.REPORT_SHARE_PLAYED).to_numpy() * df["availability"].to_numpy()
    c1 = loso_mean(df, ["type"], "actual")
    c2 = loso_mean(df, ["type", "bucket"], "actual")
    c3 = df["availability"].to_numpy() * np.clip(1 - loso_streak_mean(df) / df["left"].to_numpy(), 0, 1)
    c1_fixed = df["type"].map(ratings.REPORT_SHARE_PLAYED).to_numpy()
    out = {"rules": "docs/prereg-report-share.md",
           "C1_vs_C0": compare(df, c1, c0),
           "C2_vs_C1": compare(df, c2, c1),
           "C3_vs_C1": compare(df, c3, c1),
           "for_reference_current_shares_alone_vs_C0": compare(df, c1_fixed, c0),
           "fitted_all_seasons": {
               "share_by_type": df.assign(x=df.actual * df.left).groupby("type")[["x", "left"]].sum()
                                  .pipe(lambda g: (g.x / g.left).round(3)).to_dict(),
               "share_by_type_and_left": {f"{t}|{b}": v for (t, b), v in df.assign(x=df.actual * df.left)
                                          .groupby(["type", "bucket"])[["x", "left"]].sum()
                                          .pipe(lambda g: (g.x / g.left).round(3)).items()},
               "mean_streak_by_type": df[df.left > 20].groupby("type")["streak"].mean().round(2).to_dict(),
               "spells_by_type": df["type"].value_counts().to_dict()}}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
