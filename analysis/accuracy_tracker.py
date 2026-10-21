"""Score every saved BPV snapshot against what actually happened after its date.

The app rescores automatically (refresh(), called by /api/accuracy, when the results are over 6 hours old
or a newer snapshot exists). To run it by hand:
    python -m analysis.accuracy_tracker          (writes data/accuracy.json, shown at /api/accuracy)

For each data/snapshots/bpv_<date>.csv it compares the snapshot with the games played after that date:
- per-game error: |production - actual FPTS/game| for players with 10+ games since (mean and median),
  next to a naive benchmark (last season's FPTS/game, or this season's so far for in-season snapshots);
- ranking: rank correlation of BPV with actual total FPTS since the snapshot, over every player in the
  snapshot (a player who hasn't played counts as 0, so injuries count against the projection);
- range coverage: share of players (10+ games since) whose actual FPTS/game fell inside the likely range;
  the ranges are meant to hold about 80%.
ESPN snapshots (espn_<date>*.csv, saved by analysis/collect.py) are scored the same way, and each is
compared head to head with the BPV snapshot from the same day on the players both cover.
Each BPV snapshot is also ranked against every benchmark we can collect without permission (ESPN projections,
ESPN's crowd, last season, season so far), on one shared pool: see benchmarks() and docs/prereg-ros-benchmarks.md.
Results early in a season are noisy; the numbers mean little before ~20 games.
"""
import datetime
import glob
import json
import os
import re
import threading
import time
import warnings

import numpy as np
import pandas as pd

import bpv
import nba_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(ROOT, "data", "snapshots")
OUT = os.path.join(ROOT, "data", "accuracy.json")
MIN_GAMES = 10
AVAIL_TOP = 150           # availability check: BPV's top 150
DISAGREE_N = 20           # disagreements check: the 20 players BPV and ESPN rank most differently
TARGET_COVERAGE = 0.8


def projected_season(date):
    """The season a snapshot projects: from July on, the one starting that fall."""
    return nba_data.season_string(date.year if date.month >= 7 else date.year - 1)


def snapshot_paths():
    return sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "bpv_*.csv")) + glob.glob(os.path.join(SNAPSHOT_DIR, "espn_*.csv")))


def score(path, only_ids=None):
    m = re.search(r"(bpv|espn)_(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    source, date = m.group(1), datetime.date.fromisoformat(m.group(2))
    snap = pd.read_csv(path)
    if only_ids is not None:
        snap = snap[snap["id"].isin(only_ids)]
    season = snap["target_season"].iloc[0] if "target_season" in snap and len(snap) else projected_season(date)
    games = nba_data.player_game_logs(season)
    result = {"snapshot": os.path.basename(path), "source": source, "date": date.isoformat(), "season": season,
              "players": len(snap)}
    if games.empty:
        return {**result, "status": "no games yet"}
    games = bpv.add_fpts(games) if "FPTS" not in games else games
    if "_pre_" in os.path.basename(path):
        # A preseason snapshot projects the whole season, opening night included (it's dated opening day).
        before, after = games.iloc[0:0], games
    else:
        before = games[games["GAME_DATE"] <= date.isoformat()]
        after = games[games["GAME_DATE"] > date.isoformat()]
    if after.empty:
        return {**result, "status": "no games after the snapshot yet"}
    actual = after.groupby("PLAYER_ID")["FPTS"].agg(["mean", "size", "sum"])
    snap = snap.set_index("id")
    result["games_since"] = int(after["GAME_ID"].nunique()) if "GAME_ID" in after else None
    result["last_game"] = after["GAME_DATE"].max()

    # Naive benchmark: this season so far for in-season snapshots, otherwise last season.
    if before.empty:
        prev = nba_data.player_game_logs(nba_data.previous_season(season))
        prev = bpv.add_fpts(prev) if "FPTS" not in prev else prev
        naive, naive_name = prev.groupby("PLAYER_ID")["FPTS"].mean(), "last season FPTS/game"
    else:
        naive, naive_name = before.groupby("PLAYER_ID")["FPTS"].mean(), "season-to-date FPTS/game"

    reg = snap.join(actual, how="inner")
    reg = reg[reg["size"] >= MIN_GAMES]
    if len(reg):
        err = (reg["production"] - reg["mean"]).abs()
        both = reg.join(naive.rename("naive"), how="inner")
        result["per_game"] = {
            "players": len(reg),
            "bpv_mean_error": float(err.mean()), "bpv_median_error": float(err.median()),
            "benchmark": naive_name, "benchmark_players": len(both),
            "bpv_mean_error_same_players": float((both["production"] - both["mean"]).abs().mean()) if len(both) else None,
            "benchmark_mean_error": float((both["naive"] - both["mean"]).abs().mean()) if len(both) else None,
            "bias": float((reg["production"] - reg["mean"]).mean()),
        }
        if "range_low" in reg:
            inside = (reg["mean"] >= reg["range_low"]) & (reg["mean"] <= reg["range_high"])
            valid = reg[["range_low", "range_high"]].notna().all(axis=1)
            result["range_coverage"] = {"players": int(valid.sum()), "inside": float(inside[valid].mean()) if valid.any() else None,
                                        "target": TARGET_COVERAGE}
    totals = actual["sum"].reindex(snap.index).fillna(0)
    # Spearman = Pearson on ranks (pandas' method="spearman" needs scipy, which the live server doesn't install).
    result["ranking"] = {"players": len(snap), "spearman_bpv_vs_actual_total": float(snap["bpv"].rank().corr(totals.rank()))}
    top = snap.nsmallest(50, "rank") if "rank" in snap else snap.nlargest(50, "bpv")
    result["top50"] = {"projected_fpg": float(top["production"].mean()),
                       "actual_fpg": float(actual["mean"].reindex(top.index).mean()),
                       "share_with_10_games": float((actual["size"].reindex(top.index).fillna(0) >= MIN_GAMES).mean())}
    if "availability" in snap and "team" in snap:
        # Availability (docs/prereg-accuracy-checks.md): BPV's top 150, share of their team's games played since.
        top = snap.nsmallest(AVAIL_TOP, "rank") if "rank" in snap else snap.nlargest(AVAIL_TOP, "bpv")
        team_games = after.groupby("TEAM_ABBREVIATION")["GAME_ID"].nunique()
        tg = top["team"].map(team_games)
        top = top[tg > 0]
        played = actual["size"].reindex(top.index).fillna(0) / top["team"].map(team_games)
        result["availability"] = {"players": len(top), "predicted": float(top["availability"].mean()),
                                  "actual": float(played.clip(upper=1).mean())}
    result["days_of_games"] = int((pd.Timestamp(after["GAME_DATE"].max()) - pd.Timestamp(after["GAME_DATE"].min())).days + 1)
    result["status"] = "scored"
    return result


REFRESH_SECONDS = 6 * 3600
_refresh_lock = threading.Lock()


def refresh(max_age=REFRESH_SECONDS):
    """Rescore if the results are missing, older than max_age, older than the newest snapshot, or about a different
    set of snapshots (a deploy gives every file the same time, so times alone can't tell a stale results file)."""
    with _refresh_lock:
        paths = snapshot_paths()
        newest = max((os.path.getmtime(p) for p in paths), default=0)
        if os.path.exists(OUT):
            age = os.path.getmtime(OUT)
            try:
                with open(OUT, encoding="utf-8") as f:
                    scored = {s.get("snapshot") for s in json.load(f).get("snapshots", [])}
            except (OSError, ValueError):
                scored = None
            same_files = scored == {os.path.basename(p) for p in paths}
            if time.time() - age < max_age and age >= newest and same_files:
                return
        run(verbose=False)


def main():
    run(verbose=True)


def head_to_head(espn_path, paths, date):
    """BPV vs ESPN from the same day, on the players both projected."""
    # Same day and same kind: a preseason ESPN snapshot is paired with the preseason BPV one, not with an in-season
    # snapshot saved later that day.
    pre = "_pre_" in os.path.basename(espn_path)
    bpv_same_day = [p for p in paths if os.path.basename(p).startswith(f"bpv_{date}")
                    and ("_pre_" in os.path.basename(p)) == pre]
    if not bpv_same_day:
        return None
    common = set(pd.read_csv(espn_path)["id"]) & set(pd.read_csv(bpv_same_day[0])["id"])
    b, e = score(bpv_same_day[0], common), score(espn_path, common)
    pick = lambda r: {"players": r.get("per_game", {}).get("players"),
                      "per_game_error": r.get("per_game", {}).get("bpv_mean_error"),
                      "ranking": r.get("ranking", {}).get("spearman_bpv_vs_actual_total")}
    return {"bpv_snapshot": os.path.basename(bpv_same_day[0]), "common_players": len(common), "bpv": pick(b), "espn": pick(e),
            "disagreements": disagreements(bpv_same_day[0], espn_path, date, pre)}


def disagreements(bpv_path, espn_path, date, pre):
    """The players BPV and ESPN rank most differently: whose rank was closer to how they actually finished?"""
    b = pd.read_csv(bpv_path).drop_duplicates("id").set_index("id")
    e = pd.read_csv(espn_path).drop_duplicates("id").set_index("id")
    common = b.index.intersection(e.index)
    pool = set(b.loc[common, "bpv"].nlargest(BENCH_POOL_TOP).index) | set(e.loc[common, "bpv"].nlargest(BENCH_POOL_TOP).index)
    pool = sorted(pool)
    season = b["target_season"].iloc[0] if "target_season" in b else projected_season(datetime.date.fromisoformat(date))
    games = nba_data.player_game_logs(season)
    games = bpv.add_fpts(games) if "FPTS" not in games else games
    after = games if pre else games[games["GAME_DATE"] > date]
    if after.empty or not pool:
        return None
    totals = after.groupby("PLAYER_ID")["FPTS"].sum().reindex(pool).fillna(0)
    played = after.groupby("PLAYER_ID").size().reindex(pool).fillna(0)
    actual = totals.rank(ascending=False)
    br = b.loc[pool, "bpv"].rank(ascending=False)
    er = e.loc[pool, "bpv"].rank(ascending=False)
    top = (br - er).abs().nlargest(DISAGREE_N).index
    db, de = (br[top] - actual[top]).abs(), (er[top] - actual[top]).abs()
    wins = float((db < de).sum() + 0.5 * (db == de).sum())
    names = b.loc[top, "name"]
    closer = lambda i: "BPV" if db[i] < de[i] else "ESPN" if de[i] < db[i] else "tie"
    examples = [{"name": names[i], "bpv_rank": int(br[i]), "espn_rank": int(er[i]), "actual_rank": int(actual[i]),
                 "games": int(played[i]), "fpts": float(totals[i]), "closer": closer(i)} for i in top]   # biggest gap first
    return {"players": len(top), "bpv_closer": wins, "pool": len(pool), "examples": examples}


BENCH_POOL_TOP = 150      # pool: union of each ranker's top 150 on the snapshot date
BENCH_TOP_HITS = 130      # every roster spot in a 10-team, 13-player league
BENCH_EARLY_DAYS = 14     # results before 14 days of games are labelled early


def _same_day(prefix, date, pre):
    names = [f for f in os.listdir(SNAPSHOT_DIR) if f.startswith(f"{prefix}_{date}") and ("_pre_" in f) == pre]
    return os.path.join(SNAPSHOT_DIR, names[0]) if names else None


def _spearman(a, b):
    return float(a.rank().corr(b.rank()))       # Pearson on ranks (no scipy on the live server)


def benchmarks(bpv_path):
    """BPV's snapshot against every other ranker known on its date, on one pool (docs/prereg-ros-benchmarks.md).
    Returns None if nothing has been played since."""
    name = os.path.basename(bpv_path)
    date = re.search(r"bpv_(\d{4}-\d{2}-\d{2})", name).group(1)
    pre = "_pre_" in name
    snap = pd.read_csv(bpv_path).drop_duplicates("id").set_index("id")
    season = snap["target_season"].iloc[0] if "target_season" in snap and len(snap) else projected_season(datetime.date.fromisoformat(date))
    games = nba_data.player_game_logs(season)
    if games.empty:
        return None
    games = bpv.add_fpts(games) if "FPTS" not in games else games
    before = games.iloc[0:0] if pre else games[games["GAME_DATE"] <= date]
    after = games if pre else games[games["GAME_DATE"] > date]
    if after.empty:
        return None
    older = before.empty and not pre      # an earlier preseason snapshot (not the final one before opening night)
    pre = pre or older

    scores = {"BPV": snap["bpv"]}
    espn = _same_day("espn", date, pre)
    if espn:
        scores["ESPN projections"] = pd.read_csv(espn).drop_duplicates("id").set_index("id")["bpv"]
    crowd = _same_day("crowd", date, pre)
    if crowd:
        c = pd.read_csv(crowd).drop_duplicates("id").set_index("id")
        if pre:
            scores["ESPN crowd (draft position)"] = -c["adp"].dropna()
        else:
            scores["ESPN crowd (% rostered)"] = c["pct_owned"] + c["pct_started"] / 1000   # % started breaks ties
    prev = nba_data.player_game_logs(nba_data.previous_season(season))
    prev = bpv.add_fpts(prev) if "FPTS" not in prev else prev
    scores["Last season FPTS/game"] = prev.groupby("PLAYER_ID")["FPTS"].mean()
    if not before.empty:
        scores["Season so far FPTS/game"] = before.groupby("PLAYER_ID")["FPTS"].mean()

    pool = sorted(set().union(*(set(s.nlargest(BENCH_POOL_TOP).index) for s in scores.values())))
    outcome = after.groupby("PLAYER_ID")["FPTS"].sum().reindex(pool).fillna(0)
    actual_top = set(outcome.nlargest(BENCH_TOP_HITS).index)
    out = {}
    for k, s in scores.items():
        s = s.reindex(pool)
        filled = s.fillna(s.min() - 1 if s.notna().any() else 0)   # unscored pool players rank below everyone it scores
        top = set(filled.sort_values(ascending=False).index[:BENCH_TOP_HITS])
        out[k] = {"ranking": _spearman(filled, outcome), "top130_hits": len(top & actual_top) / BENCH_TOP_HITS,
                  "scored_in_pool": int(s.notna().sum())}
    days = (pd.Timestamp(after["GAME_DATE"].max()) - pd.Timestamp(after["GAME_DATE"].min())).days + 1
    return {"bpv_snapshot": name, "date": date, "preseason": pre, "pool": len(pool), "days_of_games": int(days),
            "early": days < BENCH_EARLY_DAYS, "older_preseason": older, "rankers": out}


def benchmark_summary(rows):
    """Average over snapshots (in-season and preseason separately) and how often BPV beat each ranker. Preseason uses
    only the final snapshot before opening night. bpv_ranking_same: BPV's average on the snapshots that ranker has."""
    summary = {}
    for kind in ("preseason", "in-season"):
        rs = [r for r in rows if r["preseason"] == (kind == "preseason") and not r.get("older_preseason")]
        if not rs:
            continue
        names = sorted({k for r in rs for k in r["rankers"]}, key=lambda k: (k != "BPV", k))
        summary[kind] = {k: {"snapshots": len(v := [r for r in rs if k in r["rankers"]]),
                             "ranking": float(np.mean([r["rankers"][k]["ranking"] for r in v])),
                             "top130_hits": float(np.mean([r["rankers"][k]["top130_hits"] for r in v])),
                             "bpv_ranking_same": float(np.mean([r["rankers"]["BPV"]["ranking"] for r in v])),
                             "bpv_better": None if k == "BPV" else
                             sum(r["rankers"]["BPV"]["ranking"] > r["rankers"][k]["ranking"] for r in v),
                             "early": all(r["early"] for r in v)} for k in names}
    return summary


def run(verbose=True):
    warnings.filterwarnings("ignore")
    paths = snapshot_paths()
    results = []
    for p in paths:
        try:
            r = score(p)
            if r.get("source") == "espn" and r.get("status") == "scored":
                r["head_to_head"] = head_to_head(p, paths, r["date"])
            results.append(r)
        except Exception as e:                        # one bad file shouldn't stop the rest
            results.append({"snapshot": os.path.basename(p), "status": f"error: {e}"})
    bench = []
    for p in paths:
        if os.path.basename(p).startswith("bpv_"):
            try:
                b = benchmarks(p)
                if b:
                    bench.append(b)
            except Exception as e:
                bench.append({"bpv_snapshot": os.path.basename(p), "error": str(e)})
    good = [b for b in bench if "error" not in b]
    out = {"updated": datetime.datetime.now().isoformat(timespec="minutes"), "snapshots": results,
           "benchmarks": {"rules": "docs/prereg-ros-benchmarks.md", "by_snapshot": bench, "summary": benchmark_summary(good)}}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    for r in (results if verbose else []):
        line = f"{r['snapshot']}: {r['status']}"
        if r.get("status") == "scored" and "per_game" in r:
            pg = r["per_game"]
            line += (f" | {pg['players']} players, BPV error {pg['bpv_mean_error']:.2f} vs {pg['benchmark']} "
                     f"{pg['benchmark_mean_error']:.2f} | rank corr {r['ranking']['spearman_bpv_vs_actual_total']:.3f}"
                     + (f" | range coverage {r['range_coverage']['inside']:.0%}" if "range_coverage" in r else ""))
        print(line)
    if verbose:
        print(f"-> {OUT}")


if __name__ == "__main__":
    main()
