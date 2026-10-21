"""Collect data without the app running: refresh NBA data, save snapshots, score them.

Run (by hand, or on a schedule by the website's host once published):
    python -m analysis.collect

Each run:
1. rebuilds BPV from fresh data (new games, injury report, rosters, ESPN), which also saves the preseason
   prior and BPV's snapshot (latest preseason one per season, then weekly in season);
2. saves ESPN's projections the same way (espn_<date>_pre_<season>.csv / espn_<date>_auto.csv), so BPV
   can be compared with ESPN on the same players, and so ESPN's in-season projections build a history;
3. rescores every snapshot (data/accuracy.json);
4. writes data/collect_status.json.
A missed day costs nothing: the next run downloads every game since.
"""
import datetime
import json
import os
import traceback
import warnings

import pandas as pd

from analysis import accuracy_tracker
import nba_data
import ratings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATUS = os.path.join(ROOT, "data", "collect_status.json")


def save_espn(meta, today, players=None):
    """ESPN's current projections, matched to NBA player ids, saved as a snapshot. players: the ratings (id, name),
    so everyone BPV rates can be matched; without it, last season's / this season's game logs are used."""
    target = meta["target_season"]
    if players is not None:
        names = players.drop_duplicates("id").set_index("id")["name"]
    else:
        names_from = nba_data.player_game_logs(meta["season"])
        names = names_from.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    by_player = ratings._espn_by_player(names, target)
    if not by_player:
        return None
    df = pd.DataFrame([{"id": pid, "name": names.get(pid, ""), "production": fpg, "games": gp, "bpv": fpg * gp}
                       for pid, (fpg, gp) in by_player.items()])
    # "bpv" holds ESPN's projected total, the score its ranking is judged on (named so the tracker treats
    # both sources alike). In season ESPN updates its numbers; whether its games are rest-of-season or
    # full-season hasn't been checked, so its in-season ranking should be read with care.
    df = df.sort_values("bpv", ascending=False).reset_index(drop=True)
    df["rank"] = range(1, len(df) + 1)
    df["target_season"] = target
    return ratings.save_snapshot(df, "espn", meta["mode"], target, today)


def save_crowd(meta, today, players, date=None):
    """ESPN's crowd numbers (% rostered, % started, ADP) matched to NBA ids, saved next to the BPV snapshot of the
    same day (crowd_<date>_auto.csv or crowd_<date>_pre_<season>.csv), so the two always share a date. Saves nothing
    on days without a BPV snapshot. date: the BPV snapshot date to pair with (default today). Returns the path or None."""
    date = date or today
    target = meta["target_season"]
    bpv_files = [f for f in os.listdir(ratings.SNAPSHOT_DIR) if f.startswith(f"bpv_{date.isoformat()}")]
    if not bpv_files:
        return None
    own = nba_data.espn_ownership(target)
    if own is None or own.empty:
        return None
    by_key = {ratings._espn_key(n): r for n, r in zip(own.PLAYER_NAME, own.itertuples())}
    names = players.drop_duplicates("id").set_index("id")["name"]
    rows = [{"id": pid, "name": n, "pct_owned": by_key[k].PCT_OWNED, "pct_started": by_key[k].PCT_STARTED,
             "adp": by_key[k].ADP} for pid, n in names.items() for k in [ratings._espn_key(n)] if k in by_key]
    df = pd.DataFrame(rows).assign(target_season=target, captured=today.isoformat())
    saved = None
    for f in bpv_files:
        kind = f"_pre_{target}" if "_pre_" in f else "_auto"
        path = os.path.join(ratings.SNAPSHOT_DIR, f"crowd_{date.isoformat()}{kind}.csv")
        if not os.path.exists(path):
            df.to_csv(path, index=False)
            saved = path
    return saved


def main():
    warnings.filterwarnings("ignore")
    today = datetime.date.today()
    status = {"started": datetime.datetime.now().isoformat(timespec="seconds"), "ok": False}
    try:
        players, meta = ratings.build()
        status.update({"mode": meta["mode"], "season": meta["season"], "target_season": meta["target_season"],
                       "players": len(players)})
        games = nba_data.player_game_logs(meta["season"])
        status["latest_game"] = games["GAME_DATE"].max() if len(games) else None
        try:
            status["espn_snapshot"] = save_espn(meta, today, players)
            status["crowd_snapshot"] = save_crowd(meta, today, players)
        except Exception as e:                       # ESPN is optional; keep collecting NBA data
            status["espn_error"] = str(e)
        accuracy_tracker.refresh(max_age=0)
        status["ok"] = True
    except Exception as e:
        status["error"] = f"{e}\n{traceback.format_exc()}"
    status["finished"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=2)
    print(json.dumps({k: v for k, v in status.items() if k != "error"}), status.get("error", ""))
    if not status["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
