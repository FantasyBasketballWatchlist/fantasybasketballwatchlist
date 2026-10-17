"""BPV (Basketball Performance Value) building blocks.

All functions work on bulk game logs from nba_data (one row per player-game or
team-game). docs/BPV-methodology.md explains the reasoning behind each piece and
analysis/backtest.py shows how the constants in ratings.py were chosen.
"""
import datetime
import re
from bisect import bisect_left, bisect_right

import numpy as np
import pandas as pd

import nba_data

# ESPN default points-league scoring.
SCORING = {"PTS": 1, "FG3M": 1, "FGA": -1, "FGM": 2, "FTA": -1, "FTM": 1,
           "REB": 1, "AST": 2, "STL": 4, "BLK": 4, "TOV": -2}

# An absence of at least this many consecutive team games is "manageable":
# long enough to put the player on IR and stream a replacement.
LONG_ABSENCE_GAMES = 5

# Players at or above this many minutes per game define the league baselines
# for availability (bench players' DNPs are mostly coach's decisions).
RELEVANT_MPG = 20

PICK_BUCKETS = [(1, 3, "1-3"), (4, 10, "4-10"), (11, 20, "11-20"), (21, 30, "21-30"), (31, 60, "31-60")]


def add_fpts(games):
    games = games.copy()
    games["FPTS"] = sum(games[stat] * weight for stat, weight in SCORING.items())
    return games


def shrink(value, n, prior, k):
    """Empirical-Bayes shrinkage: n observations of `value`, k pseudo-observations of `prior`."""
    return (n * value + k * prior) / (n + k)


def replacement_level(fpts_per_game, rank):
    """FPTS/game of the rank-th best player (the typical free agent in a league of that size)."""
    ordered = np.sort(np.asarray(fpts_per_game, dtype=float))[::-1]
    return float(ordered[min(rank, len(ordered)) - 1])


def bpv_value(production, availability, manageable, replacement):
    """Expected fantasy points per team game from rostering the player.

    When he plays you get his production; when he misses a long stretch you can
    IR him and stream a replacement; scattered one-off absences are worth nothing.
    """
    return availability * production + (1 - availability) * manageable * replacement


# ------------------------------------------------------------------ availability
def _count_between(dates, start, end):
    """Number of dates strictly between start and end."""
    return max(0, bisect_left(dates, end) - bisect_right(dates, start))


def absence_gaps(appearances, schedules, count_start=True):
    """Lengths of every run of consecutive team games a player missed in one season.

    appearances: list of (game_date, team_id) sorted by date.
    count_start: count games before the first appearance as missed. False for a
    player's debut season, when they may simply not have been signed yet.

    A gap that spans a trade is measured on whichever team's schedule gives the
    shorter gap, so moving between teams is not mistaken for an absence.
    """
    gaps = []
    first_date, first_team = appearances[0]
    if count_start:
        gaps.append(bisect_left(schedules[first_team], first_date))
    for (d1, t1), (d2, t2) in zip(appearances, appearances[1:]):
        if t1 == t2:
            gaps.append(_count_between(schedules[t1], d1, d2))
        else:
            gaps.append(min(_count_between(schedules[t1], d1, d2),
                            _count_between(schedules[t2], d1, d2)))
    last_date, last_team = appearances[-1]
    gaps.append(len(schedules[last_team]) - bisect_right(schedules[last_team], last_date))
    return [g for g in gaps if g > 0]


def season_availability(player_games, team_games, debut_player_ids=frozenset()):
    """One row per player for a season: games played, missed, and how the misses were spread.

    Columns: PLAYER_ID, PLAYER_NAME, played, missed, missed_long, spells, possible,
    mpg, fpts_pg, fpts_total, availability, manageable (share of missed games that
    came in long, IR-able stretches).
    """
    schedules = {team: sorted(dates) for team, dates in team_games.groupby("TEAM_ID")["GAME_DATE"]}
    games = add_fpts(player_games) if "FPTS" not in player_games else player_games
    rows = []
    for player_id, g in games.groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        gaps = absence_gaps(list(zip(g["GAME_DATE"], g["TEAM_ID"])), schedules,
                            count_start=player_id not in debut_player_ids)
        missed = sum(gaps)
        rows.append({
            "PLAYER_ID": player_id,
            "PLAYER_NAME": g["PLAYER_NAME"].iloc[-1],
            "played": len(g),
            "missed": missed,
            "missed_long": sum(x for x in gaps if x >= LONG_ABSENCE_GAMES),
            "spells": len(gaps),
            "possible": len(g) + missed,
            "mpg": g["MIN"].mean(),
            "fpts_pg": g["FPTS"].mean(),
            "fpts_total": g["FPTS"].sum(),
        })
    df = pd.DataFrame(rows)
    df["availability"] = df["played"] / df["possible"]
    df["manageable"] = np.where(df["missed"] > 0, df["missed_long"] / df["missed"].clip(lower=1), np.nan)
    return df


def debut_ids(seasons, player_games, draft):
    """season -> ids of players whose first NBA season it is.

    Drafted that summer, or not seen in any earlier loaded season (the earliest
    loaded season only counts that summer's draftees, since we can't see before it).
    """
    seen, out = set(), {}
    for i, s in enumerate(seasons):
        ids = set(player_games[s]["PLAYER_ID"])
        drafted = set(draft.loc[draft["SEASON"].astype(int) == nba_data.season_start_year(s), "PERSON_ID"])
        out[s] = drafted | (ids - seen) if i > 0 else drafted
        seen |= ids
    return out


def availability_history(seasons, player_games, team_games, draft):
    """Availability rows for every player-season, oldest season first.

    A relevant player (RELEVANT_MPG+ the season before) who vanishes for a whole
    season and later returns is recorded as missing that entire season.
    """
    debuts = debut_ids(seasons, player_games, draft)
    frames = []
    for s in seasons:
        a = season_availability(player_games[s], team_games[s], debuts[s])
        a["season"] = s
        frames.append(a)
    hist = pd.concat(frames, ignore_index=True)
    order = {s: i for i, s in enumerate(seasons)}
    season_len = {s: int(team_games[s].groupby("TEAM_ID").size().median()) for s in seasons}
    extra = []
    for pid, h in hist.groupby("PLAYER_ID"):
        present = {order[s] for s in h["season"]}
        for i in range(min(present) + 1, max(present)):
            prev = h[h["season"] == seasons[i - 1]]
            if i not in present and len(prev) and prev["mpg"].iloc[0] >= RELEVANT_MPG:
                n = season_len[seasons[i]]
                extra.append({"PLAYER_ID": pid, "PLAYER_NAME": prev["PLAYER_NAME"].iloc[0], "played": 0,
                              "missed": n, "missed_long": n, "spells": 1, "possible": n, "mpg": 0.0,
                              "fpts_pg": np.nan, "fpts_total": 0.0, "availability": 0.0,
                              "manageable": 1.0, "season": seasons[i]})
    if extra:
        hist = pd.concat([hist, pd.DataFrame(extra)], ignore_index=True)
    return hist


def league_availability(hist):
    """(games-played share, manageable share of misses) among relevant players."""
    rel = hist[(hist["mpg"] >= RELEVANT_MPG) | (hist["played"] == 0)]
    return (float(rel["played"].sum() / rel["possible"].sum()),
            float(rel["missed_long"].sum() / rel["missed"].sum()))


def predict_availability(hist, seasons, latest, decay, k, prior):
    """Recency-weighted, shrunk games-played share per player from seasons up to `latest`.

    `latest` gets weight 1, the season before `decay`, then decay**2, ...; the
    weighted record counts as that many games against k games of the league prior.
    """
    order = {s: i for i, s in enumerate(seasons)}
    use = hist[hist["season"].map(order) <= order[latest]]
    w = decay ** (order[latest] - use["season"].map(order))
    g = pd.DataFrame({"PLAYER_ID": use["PLAYER_ID"], "wp": w * use["played"], "wn": w * use["possible"]})
    g = g.groupby("PLAYER_ID")[["wp", "wn"]].sum()
    return shrink(g["wp"] / g["wn"].clip(lower=1e-9), g["wn"], prior, k)


# ------------------------------------------------------------------ aging
AGE_BUCKETS = ["<=21", "22-23", "24-26", "27-29", "30-32", "33+"]


def age_bucket(age):
    if age <= 21:
        return "<=21"
    if age <= 23:
        return "22-23"
    if age <= 26:
        return "24-26"
    if age <= 29:
        return "27-29"
    if age <= 32:
        return "30-32"
    return "33+"


# ------------------------------------------------------------------ schedule
def playoff_window(last_game_date):
    """ESPN's default fantasy playoffs: the last 4 Monday-Sunday weeks of the regular season."""
    last = datetime.date.fromisoformat(last_game_date)
    end = last + datetime.timedelta(days=6 - last.weekday())
    return (end - datetime.timedelta(days=27)).isoformat(), end.isoformat()


def playoff_games(schedule):
    """TEAM_ABBREVIATION -> number of games in the fantasy-playoff window."""
    start, end = playoff_window(schedule["GAME_DATE"].max())
    window = schedule[(schedule["GAME_DATE"] >= start) & (schedule["GAME_DATE"] <= end)]
    return window.groupby("TEAM_ABBREVIATION").size().to_dict()


# ------------------------------------------------------------------ injury reports
# Out with one of these in the reason: in testing, such players played a median 7% of their
# team's remaining games (vs about 60% for other injuries).
SERIOUS_INJURY = re.compile(r"surgery|tear|torn|fracture|rupture|acl|achilles|meniscus|dislocat|reconstruct", re.I)

# Share of listed players who played that day, by status (2021-22..2025-26 official reports).
PLAY_PROBABILITY = {"Available": 0.79, "Probable": 0.91, "Questionable": 0.49, "Doubtful": 0.02, "Out": 0.0}


def absence_reason(reason):
    """Category of an injury-report reason: injury, rest, g_league, personal, suspension, health_protocols, other."""
    r = str(reason)
    if "G League" in r:
        return "g_league"
    if re.search(r"\brest\b|injury management|load management", r, re.I):
        return "rest"
    if r.startswith("Injury/Illness"):
        return "injury"
    if re.search(r"personal|not with team|family|bereavement", r, re.I):
        return "personal"
    if "suspension" in r.lower():
        return "suspension"
    if "health and safety" in r.lower():
        return "health_protocols"
    return "other"


INJURY_TYPE_PATTERNS = [("sprain", re.compile(r"sprain", re.I)), ("strain", re.compile(r"strain", re.I)),
                        ("soreness", re.compile(r"soreness|tendin|contusion|bruise|inflammation|spasm|tightness|sore|"
                                                r"irritation|impingement", re.I))]


def injury_type(reason):
    """serious / sprain / strain / soreness / other (every other injury or illness), from an injury-report reason."""
    r = str(reason)
    if SERIOUS_INJURY.search(r):
        return "serious"
    for name, pattern in INJURY_TYPE_PATTERNS:
        if pattern.search(r):
            return name
    return "other"


def report_player_name(name):
    """Injury reports list 'Last, First'; return 'First Last'."""
    if "," in str(name):
        last, first = str(name).split(",", 1)
        return f"{first.strip()} {last.strip()}"
    return str(name)


# ------------------------------------------------------------------ rookies
def pick_bucket(pick):
    if pick is None or pd.isna(pick):
        return "undrafted"
    for lo, hi, name in PICK_BUCKETS:
        if lo <= pick <= hi:
            return name
    return "undrafted"


def rookie_seasons(seasons, player_games, draft, hist):
    """One row per rookie season in the loaded window (drafted rookies who never played count as 0 games)."""
    picks = draft.set_index("PERSON_ID")["OVERALL_PICK"]
    debuts = debut_ids(seasons, player_games, draft)
    rows = []
    for s in seasons[1:]:
        drafted = set(draft.loc[draft["SEASON"].astype(int) == nba_data.season_start_year(s), "PERSON_ID"])
        h = hist[(hist["season"] == s) & hist["PLAYER_ID"].isin(debuts[s])]
        for r in h.itertuples():
            rows.append({"season": s, "PLAYER_ID": r.PLAYER_ID, "bucket": pick_bucket(picks.get(r.PLAYER_ID)),
                         "fpts_pg": r.fpts_pg, "mpg": r.mpg, "played": r.played})
        for pid in drafted - set(h["PLAYER_ID"]):
            rows.append({"season": s, "PLAYER_ID": pid, "bucket": pick_bucket(picks.get(pid)),
                         "fpts_pg": np.nan, "mpg": 0.0, "played": 0})
    return pd.DataFrame(rows)


def rookie_baselines(rookies):
    """Average rookie-year production by draft-pick bucket."""
    out = {}
    for bucket, g in rookies.groupby("bucket"):
        played = g[g["played"] > 0]
        out[bucket] = {
            "rookies": int(len(g)),
            "share_who_played": float((g["played"] > 0).mean()),
            "fpts_per_game": float(played["fpts_pg"].mean()),
            "minutes_per_game": float(played["mpg"].mean()),
            "fpts_per_minute": float((played["fpts_pg"] * played["played"]).sum()
                                     / (played["mpg"] * played["played"]).sum()),
            "games_played_avg": float(g["played"].mean()),
        }
    return out
