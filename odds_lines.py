"""Sportsbook player-prop lines from The Odds API (the-odds-api.com), saved on this PC only.

The API key is yours and never goes in the repository: put it in the environment variable ODDS_API_KEY, or in the
file %USERPROFILE%\\.hoopothesis\\odds_api_key.txt (one line). The lines are saved to data/lines/, which is in .gitignore:
the API's terms forbid passing its raw data on as downloadable files, and the repository is public.

    python -m odds_lines check                       is the key working, how many credits are left (free)
    python -m odds_lines today [--markets ...]        today's lines (1 credit per market per game)
    python -m odds_lines history 2024-11-01 2025-02-28 [--markets ...] [--budget 18000] [--at-et 11:00] [--out FILE]
                                                      past lines, one snapshot an hour before each tip-off, or at a
                                                      fixed US Eastern time on game day with --at-et (e.g. 11:00 for
                                                      morning prices, into data/lines/history_morning.csv)
                                                      (paid plans only; 10 credits per market per game)
    python -m odds_lines spreads 2024-11-06 2025-01-29  past point spreads for every game, one snapshot per day at
                                                      6 PM ET (paid plans only; 10 credits per day)
    python -m odds_lines auto                         forward collection, run every 15 minutes by a scheduled task:
                                                      a morning snapshot of each of today's games (10 AM-1 PM ET) and
                                                      a closing one 0-20 minutes before its tip-off, 3 credits a game
                                                      each, into data/lines/live/<date>.csv (for closing-line value)
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
    try:
        r = requests.get(f"{API}{path}", params={"apiKey": api_key(), **params}, timeout=30)
    except requests.RequestException as e:          # its message can include the URL, and so the key
        raise RuntimeError(f"Couldn't reach The Odds API for {path}: {type(e).__name__}") from None
    Quota.remaining = r.headers.get("x-requests-remaining", Quota.remaining)
    Quota.used = r.headers.get("x-requests-used", Quota.used)
    if r.status_code == 401:
        sys.exit("The API key was refused (401). Check it was copied in full.")
    if r.status_code in (404, 422):
        return None                                    # no such event / no data for that market or time: skip it
    if r.status_code == 429:
        time.sleep(2)
        return get(path, **params)
    if not r.ok:
        # Never let the URL (it carries the key) reach an error message or a log.
        raise RuntimeError(f"The Odds API answered {r.status_code} for {path}")
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


def history(start, end, markets, budget, regions="us", at_et=None, out=None):
    """One snapshot per game, an hour before tip-off (or at `at_et`, "HH:MM" US Eastern on game day, if earlier than
    tip-off). Resumable: games already saved are skipped. Stops before going over `budget` credits in this run."""
    path = os.path.join(LINES_DIR, out or ("history_morning.csv" if at_et else "history.csv"))
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
            snap_t = tip - SNAPSHOT_BEFORE_TIP
            if at_et:
                hh, mm = map(int, at_et.split(":"))
                gd = datetime.date.fromisoformat(et_date(ev["commence_time"]))
                offset = 4 if 3 <= gd.month <= 11 else 5
                local = datetime.datetime(gd.year, gd.month, gd.day, hh, mm, tzinfo=datetime.timezone.utc) + datetime.timedelta(hours=offset)
                snap_t = min(local, tip - datetime.timedelta(minutes=30))
            snap = snap_t.strftime("%Y-%m-%dT%H:%M:%SZ")
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


def spreads(start, end, budget):
    """Point spreads for every game, from one historical snapshot per day at 22:00 UTC (6 PM ET, before most tip-offs):
    one row per game and book with the home team's spread. Resumable by date."""
    path = os.path.join(LINES_DIR, "spreads.csv")
    fields = ["game_date", "event_id", "commence", "home", "away", "snapshot", "bookmaker", "home_spread"]
    done = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            done = {r["game_date"] for r in csv.DictReader(f)}
    day, last, spent = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end), 0
    while day <= last:
        if day.isoformat() not in done:
            if spent + 10 > budget:
                print(f"Stopping at {day}: budget {budget} reached.")
                return
            data = get(f"/historical/sports/{SPORT}/odds", date=f"{day.isoformat()}T22:00:00Z", regions="us",
                       markets="spreads", oddsFormat="american")
            spent += 10
            rows = []
            for ev in (data or {}).get("data", []):
                if et_date(ev["commence_time"]) != day.isoformat():
                    continue
                for bk in ev.get("bookmakers", []):
                    for mk in bk.get("markets", []):
                        for o in mk.get("outcomes", []):
                            if o.get("name") == ev.get("home_team") and o.get("point") is not None:
                                rows.append({"game_date": day.isoformat(), "event_id": ev["id"], "commence": ev["commence_time"],
                                             "home": ev["home_team"], "away": ev["away_team"], "snapshot": data.get("timestamp"),
                                             "bookmaker": bk["key"], "home_spread": o["point"]})
            if rows:
                os.makedirs(LINES_DIR, exist_ok=True)
                new = not os.path.exists(path)
                with open(path, "a", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=fields)
                    if new:
                        w.writeheader()
                    w.writerows(rows)
            print(f"{day}: {len({r['event_id'] for r in rows})} games · remaining {Quota.remaining}", flush=True)
        day += datetime.timedelta(days=1)


LIVE_DIR = os.path.join(LINES_DIR, "live")
MORNING_HOURS_ET = (10, 13)          # the morning snapshot is taken in this window (lines are softest early)
CLOSE_WINDOW = datetime.timedelta(minutes=20)


def now_et():
    utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    return utc - datetime.timedelta(hours=4 if 3 <= utc.month <= 11 else 5)


def auto(markets=DEFAULT_MARKETS):
    """One pass of forward collection. Each game gets one 'morning' and one 'close' snapshot at most."""
    et = now_et()
    day = et.date().isoformat()
    path = os.path.join(LIVE_DIR, f"{day}.csv")
    have = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            have = {(r["event_id"], r["kind"]) for r in csv.DictReader(f)}
    events = get(f"/sports/{SPORT}/events") or []                      # free
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    todo = []
    for ev in events:
        if et_date(ev["commence_time"]) != day:
            continue
        tip = datetime.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        if tip <= utc_now:
            continue
        if MORNING_HOURS_ET[0] <= et.hour < MORNING_HOURS_ET[1] and (ev["id"], "morning") not in have:
            todo.append((ev, "morning"))
        if tip - utc_now <= CLOSE_WINDOW and (ev["id"], "close") not in have:
            todo.append((ev, "close"))
    saved = 0
    for ev, kind in todo:
        data = get(f"/sports/{SPORT}/events/{ev['id']}/odds", regions="us", markets=",".join(markets), oddsFormat="american")
        rows = rows_from_event(data, datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")) if data else []
        if not rows:
            continue                                   # props not posted yet: try again next pass
        for r in rows:
            r["kind"] = kind
        os.makedirs(LIVE_DIR, exist_ok=True)
        new = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS + ["kind"])
            if new:
                w.writeheader()
            w.writerows(rows)
        saved += 1
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} auto: {len(todo)} due, {saved} saved, credits remaining {Quota.remaining}")


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
    h.add_argument("--at-et", dest="at_et", help="snapshot time on game day, US Eastern HH:MM (e.g. 11:00)")
    h.add_argument("--out", help="file name in data/lines/")
    sub.add_parser("auto")
    sp = sub.add_parser("spreads")
    sp.add_argument("start")
    sp.add_argument("end")
    sp.add_argument("--budget", type=int, default=2000)
    a = ap.parse_args()
    if a.cmd == "check":
        check()
    elif a.cmd == "today":
        today(a.markets)
    elif a.cmd == "auto":
        auto()
    elif a.cmd == "spreads":
        spreads(a.start, a.end, a.budget)
    else:
        history(a.start, a.end, a.markets, a.budget, at_et=a.at_et, out=a.out)


if __name__ == "__main__":
    main()
