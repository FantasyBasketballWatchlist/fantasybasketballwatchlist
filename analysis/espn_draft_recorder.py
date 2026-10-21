"""Record what ESPN's league API says during a live draft, to learn whether it shares picks as they're made.

The Draft page's ESPN sync reads the same endpoint (view=mDraftDetail...). Whether ESPN updates it during the draft or
only once the draft is over hasn't been confirmed; this records it independently of any browser. Public leagues only
(no ESPN login cookies are used or stored).

    python -m analysis.espn_draft_recorder <league id> [--year 2027] [--every 10] [--start 2026-10-25T19:55] [--hours 4]

Waits until --start (local time) if given, then asks ESPN every --every seconds until the draft is complete (plus a few
minutes) or --hours have passed. Each answer goes to data/draft_recordings/<league>_<started>.jsonl (one JSON line per
check: HTTP status, ESPN's live/complete flags, picks listed, players on rosters, ESPN's last-update header), and a
one-line summary is printed. The summary at the end says when the first pick appeared relative to the draft's start.
"""
import argparse
import datetime
import json
import os
import time

import requests

API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/segments/0/leagues/{league}"
VIEWS = [("view", "mDraftDetail"), ("view", "mTeam"), ("view", "mRoster"), ("view", "mSettings")]
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "draft_recordings")
AFTER_DONE_CHECKS = 18          # keep going ~3 minutes (at 10 s) after ESPN says the draft is complete


def default_year():
    """ESPN's season id: the year the current NBA season ends (2026-27 -> 2027)."""
    today = datetime.date.today()
    return today.year + 1 if today.month >= 7 else today.year


def check(league, year):
    row = {"t": datetime.datetime.now().isoformat(timespec="seconds")}
    try:
        r = requests.get(API.format(year=year, league=league), params=VIEWS, timeout=20,
                         headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    except requests.RequestException as e:
        return {**row, "error": f"network: {e}"}
    row.update({"http": r.status_code, "espn_last_update": r.headers.get("X-Fantasy-Last-Update-League"),
                "espn_server_time": r.headers.get("X-Fantasy-Server-Time")})
    if r.status_code != 200:
        return {**row, "error": "private league (log-in needed)" if r.status_code in (401, 403) else r.text[:200]}
    d = r.json()
    dd = d.get("draftDetail") or {}
    picks = [p for p in dd.get("picks") or [] if (p.get("playerId") or 0) > 0]
    draft_at = (d.get("settings") or {}).get("draftSettings", {}).get("date")
    rostered = sum(len((t.get("roster") or {}).get("entries") or []) for t in d.get("teams") or [])
    row.update({"live": bool(dd.get("inProgress")), "done": bool(dd.get("drafted")), "picks": len(picks),
                "rostered": rostered, "draft_at": datetime.datetime.fromtimestamp(draft_at / 1000).isoformat() if draft_at else None,
                "last_picks": [[p.get("overallPickNumber"), p.get("teamId"), p.get("playerId")] for p in picks[-3:]]})
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("league")
    ap.add_argument("--year", type=int, default=default_year())
    ap.add_argument("--every", type=float, default=10.0, help="seconds between checks")
    ap.add_argument("--start", help="wait until this local time (YYYY-MM-DDTHH:MM)")
    ap.add_argument("--hours", type=float, default=4.0, help="stop after this long")
    a = ap.parse_args()

    if a.start:
        wait = (datetime.datetime.fromisoformat(a.start) - datetime.datetime.now()).total_seconds()
        if wait > 0:
            print(f"waiting {wait / 60:.0f} min until {a.start}", flush=True)
            time.sleep(wait)
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{a.league}_{datetime.datetime.now():%Y-%m-%dT%H%M}.jsonl")
    end = time.time() + a.hours * 3600
    rows, after_done = [], 0
    print(f"recording league {a.league} ({a.year}) every {a.every:g}s -> {path}", flush=True)
    while time.time() < end and after_done < AFTER_DONE_CHECKS:
        row = check(a.league, a.year)
        rows.append(row)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        print(row["t"], row.get("error") or f"live={row['live']} done={row['done']} picks={row['picks']} "
              f"rostered={row['rostered']} last_update={row['espn_last_update']}", flush=True)
        if row.get("http") in (401, 403, 404):
            break                                  # private or wrong id: nothing more to learn
        after_done += 1 if row.get("done") else 0
        time.sleep(a.every)

    ok = [r for r in rows if "picks" in r]
    first_pick = next((r for r in ok if r["picks"]), None)
    first_live = next((r for r in ok if r["live"]), None)
    growing = sum(1 for x, y in zip(ok, ok[1:]) if y["picks"] > x["picks"])
    print("\nsummary:")
    print(f"  checks: {len(rows)} ({len(ok)} answered)")
    print(f"  first 'live': {first_live['t'] if first_live else 'never'}; first pick seen: {first_pick['t'] if first_pick else 'never'}")
    print(f"  pick count went up on {growing} checks; final picks {ok[-1]['picks'] if ok else 'n/a'}")
    if ok and growing > 1:
        print("  -> ESPN shares picks DURING the draft (the count grew step by step).")
    elif ok and growing == 1:
        print("  -> ESPN shared the picks all at once (most likely only when the draft ended).")
    print(f"  saved: {path}")


if __name__ == "__main__":
    main()
