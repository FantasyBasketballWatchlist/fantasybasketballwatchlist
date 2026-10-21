"""Data access for stats.nba.com via nba_api, with an on-disk cache.

Everything BPV needs comes from a few bulk endpoints (one request per season)
instead of three requests per player:

- LeagueGameLog (player mode): every player-game of a season
- LeagueGameLog (team mode):   every team-game of a season (the schedule played)
- DraftHistory:                 every draft pick (for rookie baselines)
- LeagueDashPlayerStats:        player ages (for the age curve)
- LeagueDashPlayerBioStats:     height, weight and usage (tested for an injury-risk model)
- CommonAllPlayers:             current rosters (who plays where next season)
- ScheduleLeagueV2:             the season schedule (fantasy-playoff game counts)

Completed seasons are cached permanently; the in-progress season is refreshed
after CURRENT_SEASON_TTL seconds.

With NBA_OFFLINE=1 nothing is fetched: every dataset is read from CACHE_DIR however old it is.
The live site runs this way (stats.nba.com doesn't answer cloud servers) and reads data/live/,
which refresh.py fills from a machine that can reach the NBA.
"""
import datetime
import os
import threading
import time

import pandas as pd
from nba_api.stats.endpoints import (CommonAllPlayers, DraftHistory, LeagueDashPlayerBioStats, LeagueDashPlayerStats,
                                     LeagueGameLog, ScheduleLeagueV2)

CACHE_DIR = os.environ.get("NBA_CACHE_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cache"))
CURRENT_SEASON_TTL = int(os.environ.get("NBA_CACHE_TTL_SECONDS", 6 * 3600))
REQUEST_TIMEOUT = 60
RETRIES = 3
OFFLINE = os.environ.get("NBA_OFFLINE") == "1"

_lock = threading.RLock()   # re-entrant: a fetch may read other cached data (e.g. injury reports need the schedule)
_memory = {}
used = set()                # cache file names read this run (refresh.py copies these to data/live/)


def season_string(start_year):
    """2025 -> '2025-26'."""
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def season_start_year(season):
    """'2025-26' -> 2025."""
    return int(season[:4])


def current_season(today=None):
    """The season in progress, or the upcoming one from October on.

    Override with the NBA_SEASON environment variable (e.g. NBA_SEASON=2025-26).
    """
    override = os.environ.get("NBA_SEASON")
    if override:
        return override
    today = today or datetime.date.today()
    return season_string(today.year if today.month >= 10 else today.year - 1)


def previous_season(season):
    return season_string(season_start_year(season) - 1)


def _fetch_with_retry(fetch):
    last_error = None
    for attempt in range(RETRIES):
        try:
            return fetch()
        except Exception as e:  # network errors, timeouts, bad JSON
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise last_error


def _cached(name, fetch, is_current):
    """Return a DataFrame from memory, disk, or the network (in that order)."""
    with _lock:
        path = os.path.join(CACHE_DIR, f"{name}.csv")
        used.add(f"{name}.csv")
        entry = _memory.get(name)
        fresh_enough = lambda ts: OFFLINE or not is_current or time.time() - ts < CURRENT_SEASON_TTL
        if entry and fresh_enough(entry[1]):
            return entry[0]
        if os.path.exists(path) and fresh_enough(os.path.getmtime(path)):
            df = pd.read_csv(path, dtype={"GAME_ID": str})
            _memory[name] = (df, os.path.getmtime(path))
            return df
        if OFFLINE:
            raise FileNotFoundError(f"{path} is missing and NBA_OFFLINE=1 (run refresh.py)")
        try:
            df = _fetch_with_retry(fetch)
        except Exception:
            # Serve stale data rather than nothing if the NBA site is unreachable.
            if os.path.exists(path):
                df = pd.read_csv(path, dtype={"GAME_ID": str})
                _memory[name] = (df, time.time())
                return df
            raise
        os.makedirs(CACHE_DIR, exist_ok=True)
        df.to_csv(path, index=False)
        _memory[name] = (df, time.time())
        return df


def player_game_logs(season):
    """Every regular-season player-game for a season, oldest first."""
    def fetch():
        df = LeagueGameLog(season=season, player_or_team_abbreviation="P",
                           league_id="00", timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        return df.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)
    df = _cached(f"player_games_{season}", fetch, season == current_season())
    return df


def preseason_game_logs(season):
    """Every preseason player-game for a season (roles often show up here before opening night)."""
    def fetch():
        df = LeagueGameLog(season=season, player_or_team_abbreviation="P", season_type_all_star="Pre Season",
                           league_id="00", timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        return df.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)
    return _cached(f"preseason_games_{season}", fetch, season == current_season())


def team_game_logs(season):
    """Every regular-season team-game for a season, oldest first."""
    def fetch():
        df = LeagueGameLog(season=season, player_or_team_abbreviation="T",
                           league_id="00", timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        return df.sort_values(["GAME_DATE", "GAME_ID"]).reset_index(drop=True)
    return _cached(f"team_games_{season}", fetch, season == current_season())


def player_ages(season):
    """PLAYER_ID, PLAYER_NAME, AGE for everyone who played in a season."""
    def fetch():
        df = LeagueDashPlayerStats(season=season, timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        return df[["PLAYER_ID", "PLAYER_NAME", "AGE"]]
    return _cached(f"player_ages_{season}", fetch, season == current_season())


def player_bio(season):
    """Age, height (inches), weight and usage rate for everyone who played in a season."""
    def fetch():
        df = LeagueDashPlayerBioStats(season=season, timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        return df[["PLAYER_ID", "PLAYER_NAME", "AGE", "PLAYER_HEIGHT_INCHES", "PLAYER_WEIGHT", "USG_PCT"]]
    return _cached(f"player_bio_{season}", fetch, season == current_season())


def rosters(season):
    """PLAYER_ID, PLAYER_NAME, TEAM_ID, TEAM_ABBREVIATION for everyone currently on a roster for `season`."""
    def fetch():
        df = CommonAllPlayers(season=season, is_only_current_season=1, league_id="00",
                              timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        df = df[df["TEAM_ID"] != 0]
        return df.rename(columns={"PERSON_ID": "PLAYER_ID", "DISPLAY_FIRST_LAST": "PLAYER_NAME"})[
            ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION"]]
    # Rosters change daily in the offseason, so always refresh on the current-season schedule.
    return _cached(f"rosters_{season}", fetch, True)


def schedule(season):
    """One row per team per scheduled regular-season game: GAME_DATE, TEAM_ABBREVIATION, OPPONENT, HOME.

    Games whose teams aren't decided yet (NBA Cup knockout slots) are left out.
    """
    def fetch():
        s = ScheduleLeagueV2(season=season, league_id="00", timeout=REQUEST_TIMEOUT).get_data_frames()[0]
        s = s[s["gameId"].astype(str).str[:3] == "002"].dropna(subset=["homeTeam_teamTricode"])
        date = s["gameDateEst"].str[:10]
        home, away = s["homeTeam_teamTricode"], s["awayTeam_teamTricode"]
        return pd.concat([pd.DataFrame({"GAME_DATE": date, "TEAM_ABBREVIATION": home, "OPPONENT": away, "HOME": True}),
                          pd.DataFrame({"GAME_DATE": date, "TEAM_ABBREVIATION": away, "OPPONENT": home, "HOME": False})],
                         ignore_index=True)
    return _cached(f"team_schedule_v2_{season}", fetch, True)


INJURY_REPORT_TIMES = [(17, 30), (17, 0), (18, 30), (13, 30), (12, 30)]   # ET; the first one that exists is used


INJURY_PDF_DIR = os.path.join(CACHE_DIR, "injury_pdfs")


def _injury_report_at(ts):
    """The official NBA injury report published at `ts` (US Eastern time), or None if there isn't one.

    Needs Java and the nbainjuries package. PDFs are downloaded here with a timeout (nbainjuries'
    own requests have none), saved, and then parsed from disk.
    """
    import requests
    from nbainjuries import injury
    os.makedirs(INJURY_PDF_DIR, exist_ok=True)
    try:
        url = injury.gen_url(ts)
    except ValueError:
        return None
    path = os.path.join(INJURY_PDF_DIR, url.rsplit("/", 1)[-1])
    if not os.path.exists(path):
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        except requests.RequestException:
            return None
        if r.status_code != 200 or not r.content.startswith(b"%PDF"):
            return None
        with open(path, "wb") as f:
            f.write(r.content)
    try:
        return injury.get_reportdata(ts, local=True, localdir=INJURY_PDF_DIR, return_df=True)
    except Exception:
        return None


def _injury_report(day):
    """One report for a past game day: the first of INJURY_REPORT_TIMES that exists."""
    for hour, minute in INJURY_REPORT_TIMES:
        df = _injury_report_at(datetime.datetime(day.year, day.month, day.day, hour, minute))
        if df is not None:
            df["REPORT_DATE"] = day.isoformat()
            return df
    return None


def latest_injury_report(now_eastern=None, hours_back=36):
    """The most recent official injury report (reports come every 15 minutes on game days).

    now_eastern: current US Eastern time (naive datetime); defaults to the local clock minus the
    UTC offset difference, which is close enough for picking a 15-minute slot.
    """
    if now_eastern is None:
        utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        now_eastern = utc - datetime.timedelta(hours=4 if 3 <= utc.month <= 11 else 5)
    ts = now_eastern.replace(minute=now_eastern.minute - now_eastern.minute % 15, second=0, microsecond=0)
    for _ in range(hours_back * 4):
        df = _injury_report_at(ts)
        if df is not None and len(df):
            df["REPORT_TIME"] = ts.isoformat()
            return df
        ts -= datetime.timedelta(minutes=15)
    return None


def recent_injury_reports(days_back=4, now_eastern=None):
    """The latest report for today plus one report for each of the previous `days_back` days.

    A report lists only teams playing that day, so a player's current status is in the latest report
    that included his team's game (see ratings._latest_report_by_player).

    The result is saved to recent_injury_reports.csv; offline, that file is all there is.
    """
    path = os.path.join(CACHE_DIR, "recent_injury_reports.csv")
    used.add("recent_injury_reports.csv")
    if OFFLINE:
        return pd.read_csv(path) if os.path.exists(path) else None
    # Reports come every 15 minutes: reuse one fetched in the last 15 (the ratings and /api/injuries both ask).
    memo = _memory.get("recent_injury_reports")
    if now_eastern is None and memo and time.time() - memo[1] < RECENT_REPORTS_TTL:
        return memo[0]
    reports = _fetch_recent_injury_reports(path, days_back, now_eastern)
    if now_eastern is None:
        _memory["recent_injury_reports"] = (reports, time.time())
    return reports


RECENT_REPORTS_TTL = 15 * 60


def _fetch_recent_injury_reports(path, days_back, now_eastern):
    if now_eastern is None:
        utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        now_eastern = utc - datetime.timedelta(hours=4 if 3 <= utc.month <= 11 else 5)
    frames = []
    today = latest_injury_report(now_eastern, hours_back=12)
    if today is not None:
        today["REPORT_DATE"] = now_eastern.date().isoformat()
        frames.append(today)
    for k in range(1, days_back + 1):
        df = _injury_report(now_eastern.date() - datetime.timedelta(days=k))
        if df is not None:
            frames.append(df)
    if not frames:
        if os.path.exists(path):
            os.remove(path)     # don't leave old statuses behind for the live site
        return None
    reports = pd.concat(frames, ignore_index=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
    reports.to_csv(path, index=False)
    return reports


def injury_reports(season, dates=None):
    """One official injury report per game day of a season (2021-22 on), with one row per listed player.

    Columns: REPORT_DATE, Game Date, Matchup, Team, Player Name ("Last, First"),
    Current Status (Out / Doubtful / Questionable / Probable / Available), Reason.
    """
    def fetch():
        days = sorted(set(dates if dates is not None else team_game_logs(season)["GAME_DATE"]))
        frames = []
        for d in days:
            df = _injury_report(datetime.date.fromisoformat(d))
            if df is not None and len(df):
                frames.append(df)
            time.sleep(0.3)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return _cached(f"injury_reports_{season}", fetch, season == current_season())


ESPN_URL = ("https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/{year}/segments/0/"
            "leaguedefaults/3?view=kona_player_info")
ESPN_FILTER = '{"players":{"limit":1000,"sortPercOwned":{"sortPriority":1,"sortAsc":false}}}'
ESPN_STATS = {"PTS": "0", "BLK": "1", "STL": "2", "AST": "3", "REB": "6", "TOV": "11", "FGM": "13",
              "FGA": "14", "FTM": "15", "FTA": "16", "FG3M": "17"}
ESPN_SCORING = {"PTS": 1, "FG3M": 1, "FGA": -1, "FGM": 2, "FTA": -1, "FTM": 1, "REB": 1, "AST": 2,
                "STL": 4, "BLK": 4, "TOV": -2}


def espn_projections(season):
    """ESPN's fantasy projections for a season: PLAYER_NAME, ESPN_FPG (ESPN points scoring), ESPN_GP.

    Uses ESPN's public (undocumented) fantasy API, read-only. Before a season these are ESPN's
    preseason projections; during a season ESPN updates them to rest-of-season values.
    ESPN_OUT: ESPN expects him to miss (most of) the season: 0 projected games, or no projection while listed OUT.
    """
    def fetch():
        import requests
        year = season_start_year(season) + 1
        r = requests.get(ESPN_URL.format(year=year), headers={"X-Fantasy-Filter": ESPN_FILTER,
                                                              "User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        rows = []
        for p in r.json().get("players", []):
            pl = p["player"]
            projected = False
            for s in pl.get("stats", []):
                if s.get("statSourceId") == 1 and s.get("statSplitTypeId") == 0 and s.get("seasonId") == year:
                    avg = s.get("averageStats") or {}
                    fpg = sum(w * avg.get(ESPN_STATS[k], 0.0) for k, w in ESPN_SCORING.items())
                    gp = s["stats"].get("42", 0.0)
                    rows.append({"PLAYER_NAME": pl["fullName"], "ESPN_FPG": fpg, "ESPN_GP": gp, "ESPN_OUT": gp == 0})
                    projected = True
            if not projected and pl.get("injuryStatus") == "OUT":
                rows.append({"PLAYER_NAME": pl["fullName"], "ESPN_FPG": float("nan"), "ESPN_GP": float("nan"), "ESPN_OUT": True})
        return pd.DataFrame(rows, columns=["PLAYER_NAME", "ESPN_FPG", "ESPN_GP", "ESPN_OUT"])
    return _cached(f"espn_projections_{season}", fetch, True)


ESPN_POSITION_SLOTS = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C"}


def espn_positions(season):
    """ESPN fantasy position eligibility for a season: PLAYER_NAME, POSITIONS (e.g. "PG/SG")."""
    def fetch():
        import requests
        year = season_start_year(season) + 1
        r = requests.get(ESPN_URL.format(year=year), headers={"X-Fantasy-Filter": ESPN_FILTER,
                                                              "User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        rows = []
        for p in r.json().get("players", []):
            pl = p["player"]
            slots = [ESPN_POSITION_SLOTS[s] for s in sorted(pl.get("eligibleSlots", [])) if s in ESPN_POSITION_SLOTS]
            if slots:
                rows.append({"PLAYER_NAME": pl["fullName"], "POSITIONS": "/".join(slots)})
        return pd.DataFrame(rows, columns=["PLAYER_NAME", "POSITIONS"])
    return _cached(f"espn_positions_{season}", fetch, True)


def draft_history():
    """Every NBA draft pick (all years)."""
    def fetch():
        return DraftHistory(league_id="00", timeout=REQUEST_TIMEOUT).get_data_frames()[0]
    # Drafts happen once a year; refresh on the same schedule as the current season.
    return _cached("draft_history", fetch, True)
