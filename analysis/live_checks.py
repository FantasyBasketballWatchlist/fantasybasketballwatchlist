"""In-season self-checks, run by refresh.py after each rebuild (data/tracking/).

Some parts of BPV could not be backtested before the season, or only on small samples: the weekly "this week"
projection, the official injury report's play probabilities, incoming rookies and players returning from a
missed season. This module records those predictions when they're made and scores them once the games are
played, so the record builds itself during the season:

- week_predictions.csv: each player's expected FPTS for the rest of the Monday-Sunday week, logged at the first
  morning refresh of the week (morning only, so no game from that day has been played yet), with a simple
  benchmark (season FPTS/game x games left).
- injury_predictions.csv: at the evening refresh (after the 5:30 PM report), each listed player's status and
  play probability for his team's next game; scored as played / didn't play.
- Preseason groups: the last preseason snapshot scored per game against ESPN's projection, for rookies,
  players returning from a missed season, and everyone else.
- game_predictions.csv: the single-game projections (game_projections.py) for that day's games, logged at the first
  morning refresh, scored against the box scores (rules: docs/prereg-game-projections.md).

summary.json collects the results and any flags (a part doing worse than its benchmark on a fair sample).
Flags are for a person to look at: nothing here changes the model by itself.
"""
import datetime
import glob
import json
import os

import numpy as np
import pandas as pd

import bpv
import nba_data

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRACK_DIR = os.path.join(ROOT, "data", "tracking")
WEEK_FILE = os.path.join(TRACK_DIR, "week_predictions.csv")
INJURY_FILE = os.path.join(TRACK_DIR, "injury_predictions.csv")
GAMES_FILE = os.path.join(TRACK_DIR, "game_predictions.csv")
LOG_MIN_MINUTES = 10           # single-game projections are logged for players projected for 10+ minutes
SUMMARY_FILE = os.path.join(TRACK_DIR, "summary.json")
SNAPSHOT_DIR = os.path.join(ROOT, "data", "snapshots")

MORNING_BEFORE_HOUR = 12        # weekly projections are logged only before noon (no game played yet that day)
EVENING_FROM_HOUR = 17          # injury statuses are logged from 5 PM (after the 5:30 PM report is out by 6 PM)
# Flag rules (deliberately conservative, so a flag means something):
MIN_WEEKS = 3                   # weekly projection worse than the benchmark in most of at least this many weeks
MIN_STATUS_N = 40               # an injury status whose play rate is off by more than CALIBRATION_GAP on this many
CALIBRATION_GAP = 0.15
MIN_GROUP_N = 15                # a preseason group worse than ESPN by more than GROUP_GAP FPTS/game on this many
GROUP_GAP = 1.0
GROUP_MIN_GAMES = 10


def _read(path):
    return pd.read_csv(path) if os.path.exists(path) else None


def _append(path, new, keys):
    """Add rows whose keys aren't already logged (the first prediction of each kind is the one scored)."""
    old = _read(path)
    if old is not None and len(old):
        seen = set(map(tuple, old[keys].astype(str).to_numpy()))
        new = new[[tuple(r) not in seen for r in new[keys].astype(str).to_numpy()]]
        new = pd.concat([old, new], ignore_index=True)
    os.makedirs(TRACK_DIR, exist_ok=True)
    new.to_csv(path, index=False)


def record(players, meta, now=None):
    """Log this refresh's predictions (in season only)."""
    if meta.get("mode") != "in-season":
        return
    now = now or datetime.datetime.now()
    today = now.date()
    week_end = today + datetime.timedelta(days=6 - today.weekday())
    if now.hour < MORNING_BEFORE_HOUR and "week_fpts" in players:
        w = players[players["week_fpts"].notna() & (players["week_games"] > 0)]
        if len(w):
            _append(WEEK_FILE, pd.DataFrame({
                "logged_on": today.isoformat(), "week_end": week_end.isoformat(), "id": w["id"].astype(int),
                "name": w["name"], "team": w["team"], "rank": w["rank"], "games_left": w["week_games"],
                "predicted": w["week_fpts"].round(2), "benchmark": (w["season_fpts"] * w["week_games"]).round(2),
            }), ["week_end", "id"])
    if now.hour < MORNING_BEFORE_HOUR:
        try:
            _log_game_projections(players, meta, today)
        except Exception as e:                       # a new, untested part: never let it stop the refresh
            print(f"single-game projections not logged: {type(e).__name__}: {e}")
    if now.hour >= EVENING_FROM_HOUR and "report_status" in players:
        r = players[players["report_status"].notna() & players["play_probability"].notna()]
        if len(r):
            sched = nba_data.schedule(meta["season"])
            upcoming = sched[sched["GAME_DATE"] >= today.isoformat()].sort_values("GAME_DATE")
            next_game = upcoming.groupby("TEAM_ABBREVIATION")["GAME_DATE"].first()
            r = r.assign(game_date=r["team"].map(next_game)).dropna(subset=["game_date"])
            _append(INJURY_FILE, pd.DataFrame({
                "logged_on": today.isoformat(), "game_date": r["game_date"], "id": r["id"].astype(int),
                "name": r["name"], "team": r["team"], "status": r["report_status"],
                "play_probability": r["play_probability"].round(3),
            }), ["game_date", "id"])


def _log_game_projections(players, meta, today):
    import game_projections as gp
    proj = gp.today(players, meta, day=today.isoformat())
    if proj["players"]:
        this_g = nba_data.player_game_logs(meta["season"])
        bench = gp.benchmark(this_g[this_g["GAME_DATE"] < today.isoformat()],
                             nba_data.player_game_logs(nba_data.previous_season(meta["season"])))
        rotation = [r for r in proj["players"] if r["minutes"] >= LOG_MIN_MINUTES]     # keeps the file small
        _append(GAMES_FILE, pd.DataFrame([gp.flatten(proj["day"], r, bench.get(r["id"])) for r in rotation]), ["date", "id"])


def _weekly(games, today):
    log = _read(WEEK_FILE)
    if log is None or not len(log):
        return {"status": "no weeks logged yet"}
    done = log[log["week_end"] < today.isoformat()]
    if not len(done):
        return {"status": "first week still in progress", "logged_players": int(len(log))}
    weeks = []
    for week_end, g in done.groupby("week_end"):
        start = g["logged_on"].min()
        played = games[(games["GAME_DATE"] >= start) & (games["GAME_DATE"] <= week_end)]
        actual = played.groupby("PLAYER_ID")["FPTS"].sum()
        g = g.assign(actual=g["id"].map(actual).fillna(0.0))
        top = g[g["rank"] <= 150]
        weeks.append({"week_end": week_end, "players": int(len(g)),
                      "model_error": float((g["predicted"] - g["actual"]).abs().mean()),
                      "benchmark_error": float((g["benchmark"] - g["actual"]).abs().mean()),
                      "top150_model_error": float((top["predicted"] - top["actual"]).abs().mean()) if len(top) else None,
                      "top150_benchmark_error": float((top["benchmark"] - top["actual"]).abs().mean()) if len(top) else None})
    better = sum(w["model_error"] < w["benchmark_error"] for w in weeks)
    return {"status": "scored", "weeks": weeks, "weeks_model_better": int(better), "weeks_scored": len(weeks),
            "model_error": float(np.mean([w["model_error"] for w in weeks])),
            "benchmark_error": float(np.mean([w["benchmark_error"] for w in weeks]))}


def _injury(games, today):
    log = _read(INJURY_FILE)
    if log is None or not len(log):
        return {"status": "no injury reports logged yet"}
    last_game = games["GAME_DATE"].max() if len(games) else ""
    done = log[(log["game_date"] < today.isoformat()) & (log["game_date"] <= last_game)]
    if not len(done):
        return {"status": "waiting for games", "logged": int(len(log))}
    played = set(zip(games["PLAYER_ID"], games["GAME_DATE"]))
    done = done.assign(played=[(i, d) in played for i, d in zip(done["id"], done["game_date"])])
    by_status = {s: {"n": int(len(g)), "predicted": float(g["play_probability"].mean()), "actual": float(g["played"].mean())}
                 for s, g in done.groupby("status")}
    brier = float(((done["play_probability"] - done["played"]) ** 2).mean())
    return {"status": "scored", "listings": int(len(done)), "brier": brier, "by_status": by_status}


def _preseason_groups(games, season):
    snaps = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, f"bpv_*_pre_{season}.csv")))
    if not snaps or not len(games):
        return {"status": "no preseason snapshot or no games yet"}
    snap = pd.read_csv(snaps[-1])
    if "espn_fpg" not in snap:
        return {"status": "snapshot has no ESPN column"}
    actual = games.groupby("PLAYER_ID")["FPTS"].agg(["mean", "size"])
    d = snap.join(actual, on="id", how="inner")
    d = d[d["size"] >= GROUP_MIN_GAMES]
    note = d["production_note"].fillna("")
    groups = {"incoming rookies": d["rookie"].astype(bool), "returning from a missed season": note.str.startswith("missed all"),
              "everyone else": ~d["rookie"].astype(bool) & ~note.str.startswith("missed all")}
    out = {"status": "scored", "snapshot": os.path.basename(snaps[-1]), "min_games": GROUP_MIN_GAMES, "groups": {}}
    for name, m in groups.items():
        g = d[m & d["espn_fpg"].notna()]
        out["groups"][name] = {"players": int(len(g)),
                               "bpv_error": float((g["production"] - g["mean"]).abs().mean()) if len(g) else None,
                               "espn_error": float((g["espn_fpg"] - g["mean"]).abs().mean()) if len(g) else None}
    return out


def _games(games):
    try:
        import game_projections as gp
        log = _read(GAMES_FILE)
        return gp.score(log, games) if log is not None else {"status": "nothing logged yet"}
    except Exception as e:
        return {"status": f"error: {type(e).__name__}: {e}"}


def _flags(summary):
    flags = []
    w = summary["weekly"]
    if w.get("status") == "scored" and w["weeks_scored"] >= MIN_WEEKS and w["weeks_model_better"] * 2 < w["weeks_scored"]:
        flags.append(f"Weekly projections were worse than the simple benchmark in {w['weeks_scored'] - w['weeks_model_better']} "
                     f"of {w['weeks_scored']} weeks ({w['model_error']:.1f} vs {w['benchmark_error']:.1f} FPTS error).")
    for status, s in summary["injury"].get("by_status", {}).items():
        if s["n"] >= MIN_STATUS_N and abs(s["predicted"] - s["actual"]) > CALIBRATION_GAP:
            flags.append(f"Injury status '{status}': predicted {s['predicted']:.0%} to play, actually {s['actual']:.0%} "
                         f"({s['n']} listings).")
    for name, g in summary["preseason"].get("groups", {}).items():
        if g["players"] >= MIN_GROUP_N and g["bpv_error"] - g["espn_error"] > GROUP_GAP:
            flags.append(f"Preseason projections for {name} were worse than ESPN's: {g['bpv_error']:.1f} vs "
                         f"{g['espn_error']:.1f} FPTS/game error ({g['players']} players).")
    return flags


def score(season, today=None):
    """Score everything that has matured; returns the summary (also written to summary.json if it changed)."""
    today = today or datetime.date.today()
    games = nba_data.player_game_logs(season)
    games = bpv.add_fpts(games) if len(games) and "FPTS" not in games else games
    summary = {"season": season, "weekly": _weekly(games, today), "injury": _injury(games, today),
               "preseason": _preseason_groups(games, season), "games": _games(games)}
    summary["flags"] = _flags(summary)
    old = None
    if os.path.exists(SUMMARY_FILE):
        with open(SUMMARY_FILE, encoding="utf-8") as f:
            old = json.load(f)
    if old is None or {k: v for k, v in old.items() if k != "updated"} != json.loads(json.dumps(summary)):
        summary["updated"] = today.isoformat()      # date only, and only when something changed
        os.makedirs(TRACK_DIR, exist_ok=True)
        with open(SUMMARY_FILE, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=1)
        return summary, (old or {}).get("flags", [])
    return old, old.get("flags", [])
