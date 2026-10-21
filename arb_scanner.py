"""Arbitrage scanner for NBA player props, with phone alerts (runs on this PC only).

An arbitrage: the over at one book and the under at another, same player, stat and line, priced so that betting both
returns a profit whichever side wins (1/over_odds + 1/under_odds < 1, in decimal odds).

Prices come from PropLine (prop-line.com, free key: 1,000 requests a day; one request covers every game) when its key
is saved, otherwise from The Odds API (odds_lines.py's key) within a hard credit cap per run. Keys and the alert topic
live outside the repository:
    %USERPROFILE%\\.hoopothesis\\propline_key.txt     PropLine API key (or env PROPLINE_API_KEY)
    %USERPROFILE%\\.hoopothesis\\ntfy_topic.txt       private ntfy.sh topic for phone alerts (or env NTFY_TOPIC)
    %USERPROFILE%\\.hoopothesis\\arb_settings.json    optional: {"stake": 200, "min_profit": 0.005, "max_profit": 0.05}

    python -m arb_scanner scan [--provider propline|oddsapi] [--max-credits 30] [--dry-run]
    python -m arb_scanner scheduled                  what the scheduled task runs (every 3 minutes, 5 PM-midnight):
                                                     a PropLine scan if its key is saved, otherwise nothing (it never
                                                     spends The Odds API credits)
    python -m arb_scanner test                       arbitrage math on the saved 2024-25 prices (no requests)
    python -m arb_scanner off / on                   turn the scheduled scans (and phone alerts) off or back on

Only books licensed in Virginia are used. Alerts are sent once per opportunity (again only if it gets better by 0.5
points). Every scan and alert is logged to data/lines/arb_log.csv / arb_alerts.csv (gitignored); a summary without odds
goes to data/tracking/arb_status.json for the Betting tab.
"""
import argparse
import csv
import datetime
import json
import os
import sys

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.join(os.path.expanduser("~"), ".hoopothesis")
LINES = os.path.join(ROOT, "data", "lines")
STATUS = os.path.join(ROOT, "data", "tracking", "arb_status.json")
MARKETS = ["player_points", "player_rebounds", "player_assists", "player_threes", "player_points_rebounds_assists"]
MARKET_LABEL = {"player_points": "points", "player_rebounds": "rebounds", "player_assists": "assists",
                "player_threes": "threes", "player_points_rebounds_assists": "pts+reb+ast"}
# Licensed in Virginia (keys as The Odds API / PropLine name them).
VIRGINIA = {"draftkings": "DraftKings", "fanduel": "FanDuel", "betmgm": "BetMGM", "williamhill_us": "Caesars",
            "betrivers": "BetRivers", "fanatics": "Fanatics", "espnbet": "ESPN Bet", "hardrockbet": "Hard Rock",
            "ballybet": "Bally Bet", "bet365": "bet365", "thescore": "theScore Bet"}
DEFAULTS = {"stake": 200.0, "min_profit": 0.005, "max_profit": 0.05, "hours_ahead": 8}
REALERT_GAIN = 0.005


def _secret(env, name):
    v = os.environ.get(env, "").strip()
    p = os.path.join(HOME, name)
    if not v and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            v = f.read().strip()
    return v or None


def settings():
    s = dict(DEFAULTS)
    p = os.path.join(HOME, "arb_settings.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            s.update(json.load(f))
    return s


def decimal(american):
    a = float(american)
    return 1 + a / 100 if a > 0 else 1 + 100 / abs(a)


def american(dec):
    return f"+{round((dec - 1) * 100)}" if dec >= 2 else f"{round(-100 / (dec - 1))}"


# ---------- prices

def fetch_propline(key, hours):
    """Every NBA game's props in one request (the-odds-api format)."""
    r = requests.get("https://api.prop-line.com/v1/sports/basketball_nba/odds", headers={"X-API-Key": key},
                     params={"markets": ",".join(MARKETS)}, timeout=30)
    if r.status_code == 429:
        raise RuntimeError("PropLine daily limit reached")
    if not r.ok:
        raise RuntimeError(f"PropLine answered {r.status_code}")
    return _upcoming(r.json(), hours), {"requests_left": r.headers.get("x-daily-remaining")}


def fetch_oddsapi(max_credits, hours):
    """The Odds API: free event list, then 1 credit per market per game, stopping at max_credits."""
    import odds_lines as ol
    events = _upcoming(ol.get(f"/sports/{ol.SPORT}/events") or [], hours)
    out, spent = [], 0
    for ev in events:
        if spent + len(MARKETS) > max_credits:
            break
        data = ol.get(f"/sports/{ol.SPORT}/events/{ev['id']}/odds", regions="us", markets=",".join(MARKETS), oddsFormat="american")
        spent += len(MARKETS)
        if data:
            out.append(data)
    return out, {"credits_left": ol.Quota.remaining, "credits_spent": spent}


def _upcoming(events, hours):
    now = datetime.datetime.now(datetime.timezone.utc)
    keep = []
    for ev in events or []:
        t = datetime.datetime.fromisoformat(ev["commence_time"].replace("Z", "+00:00"))
        if now < t <= now + datetime.timedelta(hours=hours):
            keep.append(ev)
    return keep


# ---------- arbitrage

def find_arbs(events, min_profit, max_profit):
    """Best over and best under (different Virginia books) for each player/stat/line; keep those that lock in a profit."""
    best = {}
    for ev in events:
        for bk in ev.get("bookmakers", []):
            if bk["key"] not in VIRGINIA:
                continue
            for mk in bk.get("markets", []):
                if mk["key"] not in MARKET_LABEL:
                    continue
                for o in mk.get("outcomes", []):
                    if o.get("point") is None or o.get("price") is None or o.get("name") not in ("Over", "Under"):
                        continue
                    k = (ev["id"], o.get("description"), mk["key"], float(o["point"]))
                    side = o["name"].lower()
                    d = decimal(o["price"])
                    cur = best.setdefault(k, {"event": ev, "over": None, "under": None})
                    if cur[side] is None or d > cur[side][0]:
                        cur[side] = (d, bk["key"])
    arbs = []
    for (eid, player, market, line), v in best.items():
        if not v["over"] or not v["under"] or v["over"][1] == v["under"][1]:
            continue
        (do, bo), (du, bu) = v["over"], v["under"]
        s = 1 / do + 1 / du
        profit = 1 / s - 1
        if profit < min_profit:
            continue
        ev = v["event"]
        arbs.append({"event_id": eid, "game": f"{ev.get('away_team')} @ {ev.get('home_team')}", "tip": ev["commence_time"],
                     "player": player, "market": market, "stat": MARKET_LABEL[market], "line": line,
                     "over_book": bo, "over_dec": do, "under_book": bu, "under_dec": du, "profit": profit,
                     "suspicious": profit > max_profit})
    return sorted(arbs, key=lambda a: -a["profit"])


def stakes(a, total):
    """Whole-dollar stakes near an even split of about `total` that lock in the most: (over $, under $, locked profit).
    The locked profit is the worse of the two outcomes; it can be 0 or less when rounding eats a tiny arbitrage."""
    s = 1 / a["over_dec"] + 1 / a["under_dec"]
    io, iu = total * (1 / a["over_dec"]) / s, total * (1 / a["under_dec"]) / s
    best = None
    for so in range(max(1, int(io) - 2), int(io) + 3):
        for su in range(max(1, int(iu) - 2), int(iu) + 3):
            lock = min(so * a["over_dec"], su * a["under_dec"]) - so - su
            if best is None or lock > best[2]:
                best = (so, su, lock)
    return best


def message(a, total):
    so, su, lock = stakes(a, total)
    tip = datetime.datetime.fromisoformat(a["tip"].replace("Z", "+00:00"))
    et = tip - datetime.timedelta(hours=4 if 3 <= tip.month <= 11 else 5)
    title = f"Arb {a['profit']:.1%}: {a['player']} {a['stat']} {a['line']}"
    body = (f"OVER {a['line']} {american(a['over_dec'])} at {VIRGINIA[a['over_book']]}: bet ${so}\n"
            f"UNDER {a['line']} {american(a['under_dec'])} at {VIRGINIA[a['under_book']]}: bet ${su}\n"
            f"Locks in ${lock:.2f} either way. {a['game']}, tip {et:%I:%M %p} ET.\n"
            f"Check both prices are still there before betting; place the bigger or riskier side first.")
    if a["suspicious"]:
        body += "\nUNUSUALLY BIG: may be a pricing error the book could cancel. Skip unless you're sure."
    return title, body


def notify(topic, title, body, priority="high"):
    r = requests.post(f"https://ntfy.sh/{topic}", data=body.encode("utf-8"),
                      headers={"Title": title.encode("ascii", "replace").decode(), "Priority": priority, "Tags": "basketball"}, timeout=15)
    return r.ok


# ---------- bookkeeping

def _append(path, row, fields):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        if new:
            w.writeheader()
        w.writerow(row)


def already_sent():
    p = os.path.join(LINES, "arb_alerts.csv")
    best = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = (r["event_id"], r["player"], r["market"], r["line"])
                best[k] = max(best.get(k, 0.0), float(r["profit"]))
    return best


def write_status(provider, n_events, arbs, alerts_sent, info):
    """Counts only (no odds) for the Betting tab."""
    p = os.path.join(LINES, "arb_alerts.csv")
    total = recent = 0
    sizes = []
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        total = len(rows)
        week = (datetime.datetime.now() - datetime.timedelta(days=7)).isoformat()
        recent = sum(r["time"] >= week for r in rows)
        sizes = [float(r["profit"]) for r in rows]
    st = {"updated": datetime.datetime.now().isoformat(timespec="minutes"), "provider": provider, "last_scan_games": n_events,
          "last_scan_arbs": len(arbs), "alerts_total": total, "alerts_last_7_days": recent,
          "median_profit": sorted(sizes)[len(sizes) // 2] if sizes else None}
    os.makedirs(os.path.dirname(STATUS), exist_ok=True)
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)


def scan(provider=None, max_credits=30, dry_run=False):
    cfg = settings()
    key = _secret("PROPLINE_API_KEY", "propline_key.txt")
    provider = provider or ("propline" if key else "oddsapi")
    if provider == "propline":
        if not key:
            sys.exit(f"No PropLine key: save it in {os.path.join(HOME, 'propline_key.txt')}")
        events, info = fetch_propline(key, cfg["hours_ahead"])
    else:
        events, info = fetch_oddsapi(max_credits, cfg["hours_ahead"])
    arbs = find_arbs(events, cfg["min_profit"], 1.0)
    for a in arbs:
        a["suspicious"] = a["profit"] > cfg["max_profit"]
    topic = _secret("NTFY_TOPIC", "ntfy_topic.txt")
    sent_before = already_sent()
    sent = 0
    now = datetime.datetime.now().isoformat(timespec="seconds")
    for a in arbs:
        k = (a["event_id"], a["player"], a["market"], str(a["line"]))
        if k in sent_before and a["profit"] < sent_before[k] + REALERT_GAIN:
            continue
        if stakes(a, cfg["stake"])[2] < 0.25:          # rounding to whole dollars leaves (almost) nothing: not worth it
            continue
        title, body = message(a, cfg["stake"])
        ok = False
        if not dry_run and topic:
            try:
                ok = notify(topic, title, body)
            except requests.RequestException:
                ok = False
        print(f"{title}\n{body}\n")
        if not dry_run:
            so, su, lock = stakes(a, cfg["stake"])
            _append(os.path.join(LINES, "arb_alerts.csv"),
                    {"time": now, "event_id": a["event_id"], "game": a["game"], "player": a["player"], "market": a["market"],
                     "line": a["line"], "over_book": a["over_book"], "over_dec": round(a["over_dec"], 4), "under_book": a["under_book"],
                     "under_dec": round(a["under_dec"], 4), "profit": round(a["profit"], 5), "stake_over": so, "stake_under": su,
                     "locked": round(lock, 2), "suspicious": a["suspicious"], "notified": ok},
                    ["time", "event_id", "game", "player", "market", "line", "over_book", "over_dec", "under_book", "under_dec",
                     "profit", "stake_over", "stake_under", "locked", "suspicious", "notified"])
            sent += 1
    if not dry_run:
        _append(os.path.join(LINES, "arb_log.csv"), {"time": now, "provider": provider, "games": len(events), "arbs": len(arbs),
                                                      "alerts": sent, "info": json.dumps(info)},
                ["time", "provider", "games", "arbs", "alerts", "info"])
        write_status(provider, len(events), arbs, sent, info)
    print(f"{now} {provider}: {len(events)} upcoming games, {len(arbs)} arbs, {sent} new alerts"
          + ("" if topic or dry_run else " (no ntfy topic saved: alerts printed only)") + f" | {info}")
    return arbs


def test():
    """The arbitrage math on the saved 2024-25 prices: rebuild each snapshot as events and count arbs."""
    import pandas as pd
    d = pd.read_csv(os.path.join(LINES, "history.csv"))
    d = d[d["market"].isin(MARKET_LABEL)]
    events = []
    for eid, g in d.groupby("event_id"):
        ev = {"id": eid, "home_team": g["home"].iloc[0], "away_team": g["away"].iloc[0], "commence_time": g["commence"].iloc[0], "bookmakers": []}
        for bk, gb in g.groupby("bookmaker"):
            mks = []
            for mk, gm in gb.groupby("market"):
                mks.append({"key": mk, "outcomes": [{"name": r.side, "description": r.player, "price": r.price, "point": r.line} for r in gm.itertuples()]})
            ev["bookmakers"].append({"key": bk, "markets": mks})
        events.append(ev)
    arbs = find_arbs(events, 1e-9, 1.0)
    print(f"{len(events)} games, {len(arbs)} arbitrages ({len(arbs) / len(events):.2f} a game)")
    if arbs:
        ps = sorted(a["profit"] for a in arbs)
        print(f"median {ps[len(ps) // 2]:.2%}, top {ps[-1]:.2%}")
        a = arbs[len(arbs) // 2]
        so, su, lock = stakes(a, 200)
        print("example:", message(a, 200)[0], "|", so, su, round(lock, 2))
        # Check the stake split: both outcomes pay at least the total staked.
        worth = 0
        for a in arbs:
            so, su, lock = stakes(a, 200)
            assert abs(min(so * a["over_dec"], su * a["under_dec"]) - so - su - lock) < 1e-9
            worth += lock >= 0.25
        print(f"stake check passed; {worth} of {len(arbs)} lock in 25 cents or more at $200 (the rest would be skipped)")
        locks = sorted(stakes(a, 200)[2] for a in arbs if stakes(a, 200)[2] >= 0.25)
        print(f"at $200 per arb: median locked ${locks[len(locks) // 2]:.2f}, total ${sum(locks):.0f} over {len(events)} games "
              f"(${sum(locks) / len(events) * 10:.0f} per 10-game night, if every one were caught in time)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan")
    s.add_argument("--provider", choices=["propline", "oddsapi"])
    s.add_argument("--max-credits", type=int, default=30)
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("test")
    sub.add_parser("scheduled")
    sub.add_parser("on")
    sub.add_parser("off")
    a = ap.parse_args()
    if a.cmd in ("on", "off"):
        import subprocess
        verb = "Enable-ScheduledTask" if a.cmd == "on" else "Disable-ScheduledTask"
        r = subprocess.run(["powershell", "-NoProfile", "-Command", f"{verb} -TaskName 'Hoopothesis arb scanner' | Select-Object -ExpandProperty State"],
                           capture_output=True, text=True)
        print(f"Arb scanner: {r.stdout.strip() or r.stderr.strip()}")
        sys.exit(0)
    if a.cmd == "test":
        test()
    elif a.cmd == "scheduled":
        if _secret("PROPLINE_API_KEY", "propline_key.txt"):
            try:
                scan("propline")
            except Exception as e:                       # log and carry on; the next run tries again
                print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} scan failed: {type(e).__name__}: {e}")
        else:
            print(f"{datetime.datetime.now():%Y-%m-%d %H:%M} waiting for a PropLine key ({os.path.join(HOME, 'propline_key.txt')})")
    else:
        scan(a.provider, a.max_credits, a.dry_run)
