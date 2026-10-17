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
    result["ranking"] = {"players": len(snap), "spearman_bpv_vs_actual_total": float(snap["bpv"].corr(totals, method="spearman"))}
    top = snap.nsmallest(50, "rank") if "rank" in snap else snap.nlargest(50, "bpv")
    result["top50"] = {"projected_fpg": float(top["production"].mean()),
                       "actual_fpg": float(actual["mean"].reindex(top.index).mean()),
                       "share_with_10_games": float((actual["size"].reindex(top.index).fillna(0) >= MIN_GAMES).mean())}
    result["status"] = "scored"
    return result


REFRESH_SECONDS = 6 * 3600
_refresh_lock = threading.Lock()


def refresh(max_age=REFRESH_SECONDS):
    """Rescore if the results are missing, older than max_age, or older than the newest snapshot."""
    with _refresh_lock:
        paths = snapshot_paths()
        newest = max((os.path.getmtime(p) for p in paths), default=0)
        if os.path.exists(OUT):
            age = os.path.getmtime(OUT)
            if time.time() - age < max_age and age >= newest:
                return
        run(verbose=False)


def main():
    run(verbose=True)


def head_to_head(espn_path, paths, date):
    """BPV vs ESPN from the same day, on the players both projected."""
    bpv_same_day = [p for p in paths if os.path.basename(p).startswith(f"bpv_{date}")]
    if not bpv_same_day:
        return None
    common = set(pd.read_csv(espn_path)["id"]) & set(pd.read_csv(bpv_same_day[0])["id"])
    b, e = score(bpv_same_day[0], common), score(espn_path, common)
    pick = lambda r: {"players": r.get("per_game", {}).get("players"),
                      "per_game_error": r.get("per_game", {}).get("bpv_mean_error"),
                      "ranking": r.get("ranking", {}).get("spearman_bpv_vs_actual_total")}
    return {"bpv_snapshot": os.path.basename(bpv_same_day[0]), "common_players": len(common), "bpv": pick(b), "espn": pick(e)}


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
    out = {"updated": datetime.datetime.now().isoformat(timespec="minutes"), "snapshots": results}
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
