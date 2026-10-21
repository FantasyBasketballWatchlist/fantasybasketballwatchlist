"""Sportsbook player-prop lines from The Odds API (the-odds-api.com), saved on this PC only.

The API key is yours and never goes in the repository: put it in the environment variable ODDS_API_KEY, or in the
file %USERPROFILE%\\.hoopothesis\\odds_api_key.txt (one line). The lines are saved to data/lines/, which is in .gitignore:
the API's terms forbid passing its raw data on as downloadable files, and the repository is public.

    python -m odds_lines check                       is the key working, how many credits are left (free)
    python -m odds_lines today [--markets ...]        today's lines (1 credit per market per game)
    python -m odds_lines history 2024-11-01 2025-02-28 [--markets ...] [--budget 18000]
                                                      past lines, one snapshot an hour before each tip-off
                                                      (paid plans only; 10 credits per market per game)
"""
import argparse
import csv
import datetime
import json
import os
import sys
import time

import requests

API = "https://api.the-odds-api.com/v4"
SPORT = "basketball_nba"
ROOT = os.path.dirname(os.path.abspath(__file__))
LINES_DIR = os.path.join(ROOT, "data", "lines")
KEY_FILE = os.path.join(os.path.expanduser("~"), ".hoopothesis", "odds_api_key.txt")
DEFAULT_MARKETS = ["player_points", "player_rebounds", "player_assists"]
MARKET_STAT = {"player_points": "PTS", "player_rebounds": "REB", "player_assists": "AST", "player_threes": "FG3M",
               "player_points_rebounds_assists": "PRA", "player_steals": "STL", "player_blocks": "BLK",
               "player_turnovers": "TOV"}
FIELDS = ["game_date", "event_id", "commence", "home", "away", "snapshot", "bookmaker", "market", "stat", "player",
          "side", "line", "price"]
SNAPSHOT_BEFORE_TIP = datetime.timedelta(hours=1)


def api_key():
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key and os.path.exists(KEY_FILE):
        with open(KEY_FILE, encoding="utf-8") as f:
            key = f.read().strip()
    if not key:
        sys.exit(f"No API key: set ODDS_API_KEY or put it in {KEY_FILE}")
    return key


class Quota:
    remaining = None
    used = None


def get(path, **params):
    r = requests.get(f"{API}{path}", params={"apiKey": api_key(), **params}, timeout=30)
    Quota.remaining = r.headers.get("x-requests-remaining", Quota.remaining)
    Quota.used = r.headers.get("x-requests-used", Quota.used)
    if r.status_code == 401:
        sys.exit("The API key was refused (401). Check it was copied in full.")
    if r.status_code == 422:
        return None                                    # e.g. no data for that market/time
    if r.status_code == 429:
        time.sleep(2)
        return get(path, **params)
    r.raise_for_status()
    return r.json()


def et_date(iso):
    """The US Eastern game date of an ISO UTC time (EDT/EST by month, as elsewhere in the app)."""
    t = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).replace(tzinfo=None)
    return (t - datetime.timedelta(hours=4 if 3 <= t.month <= 11 else 5)).date().isoformat()


def rows_from_event(ev, snapshot):
    out = []
    for bk in ev.get("bookmakers", []):
        for mk in bk.get("markets", []):
            for o in mk.get("outcomes", []):
                if o.get("point") is None:
                    continue
                out.append({"game_date": et_date(ev["commence_time"]), "event_id": ev["id"], "commence": ev["commence_time"],
                            "home": ev.get("home_team"), "away": ev.get("away_team"), "snapshot": snapshot,
                            "bookmaker": bk["key"], "market": mk["key"], "stat": MARKET_STAT.get(mk["key"], mk["key"]),
                            "player": o.get("description"), "side": o.get("name"), "line": o.get("point"), "price": o.get("price")})
    return out


def append(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerows(rows)


def check():
    sports = get("/sports")                            # free: doesn't use credits
    nba = [s for s in sports if s["key"] == SPORT]
    print(f"Key works. Credits used {Quota.used}, remaining {Quota.remaining}. NBA listed: {bool(nba)}")


def today(markets, regions="us"):
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    events = get(f"/sports/{SPORT}/events", commenceTimeFrom=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                 commenceTimeTo=(now + datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")) or []
    rows = []
    for ev in events:
        data = get(f"/sports/{SPORT}/events/{ev['id']}/odds", regions=regions, markets=",".join(markets), oddsFormat="american")
        if data:
            rows += rows_from_event(data, now.isoformat())
    if rows:
        append(os.path.join(LINES_DIR, f"lines_{rows[0]['game_date']}.csv"), rows)
    print(f"{len(events)} games, {len(rows)} prices saved. Credits remaining {Quota.remaining}.")


def history(start, end, markets, budget, regions="us"):
    """One snapshot per game, an hour before tip-off. Resumable: games already saved are skipped. Stops before going
    over `budget` credits in this run."""
    path = os.path.join(LINES_DIR, "history.csv")
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            done = {r["event_id"] for r in csv.DictReader(f)}
    spent, saved_games = 0, 0
    day = datetime.date.fromisoformat(start)
    last = datetime.date.fromisoformat(end)
    per_game = 10 * len(markets) * len(regions.split(","))
    while day <= last:
        # Events listed at noon UTC that day, starting within the next 24 hours.
        listing = get(f"/historical/sports/{SPORT}/events", date=f"{day.isoformat()}T12:00:00Z",
                      commenceTimeFrom=f"{day.isoformat()}T12:00:00Z",
                      commenceTimeTo=f"{(day + datetime.timedelta(days=1)).isoformat()}T12:00:00Z")
        spent += 1
        events = (listing or {}).get("data", [])
        for ev in events:
            if ev["id"] in done:
                continue
            if spent + per_game > budget:
                print(f"Stopping: the next game would go over the budget ({budget}). Saved {saved_games} games this run.")
                return
            tip = datetime.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
            snap = (tip - SNAPSHOT_BEFORE_TIP).strftime("%Y-%m-%dT%H:%M:%SZ")
            data = get(f"/historical/sports/{SPORT}/events/{ev['id']}/odds", date=snap, regions=regions,
                       markets=",".join(markets), oddsFormat="american")
            spent += per_game
            payload = (data or {}).get("data")
            rows = rows_from_event(payload, (data or {}).get("timestamp", snap)) if payload else []
            if rows:
                append(path, rows)
                saved_games += 1
            done.add(ev["id"])
        print(f"{day}: {len(events)} games · credits used this run ~{spent} · remaining {Quota.remaining}", flush=True)
        day += datetime.timedelta(days=1)
    print(f"Done. Saved {saved_games} games this run to {path}.")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    t = sub.add_parser("today")
    t.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    h = sub.add_parser("history")
    h.add_argument("start")
    h.add_argument("end")
    h.add_argument("--markets", nargs="+", default=DEFAULT_MARKETS)
    h.add_argument("--budget", type=int, default=18000)
    a = ap.parse_args()
    if a.cmd == "check":
        check()
    elif a.cmd == "today":
        today(a.markets)
    else:
        history(a.start, a.end, a.markets, a.budget)


if __name__ == "__main__":
    main()
