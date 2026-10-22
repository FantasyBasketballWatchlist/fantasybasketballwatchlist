"""Compute BPV for every player in the league.

BPV = availability x production + (1 - availability) x manageable share x replacement

- production:   FPTS per game from the season, adjusted for recent form (minutes
                changes count more than hot/cold shooting), new roles, and, early
                in the season, last season's level (age-adjusted) or a draft-slot
                baseline. Between seasons: last season's average plus an age
                adjustment and a roster-crowding adjustment for next season's team.
                Teammates of a player marked out long-term get a boost.
- availability: share of team games he is expected to play, from recent seasons,
                shrunk heavily toward the league average.
- manageable:   share of missed games that come in long, IR-able stretches (the
                league average: one player's pattern is too noisy to measure).
- replacement:  FPTS/game of a typical free agent (the Nth best player, N = league
                teams x roster size; 130 by default).

Constants were chosen by analysis/backtest.py (results.json); the age curve by
analysis/preseason_production.py; roster crowding by analysis/test_minutes_model.py;
the teammate boost, early-season age prior and ranges by analysis/test_misc.py and
analysis/test_schedule_positions_uncertainty.py. Rejected ideas are listed in
docs/BPV-methodology.md.
"""
import datetime
import json
import os
import re
import threading
import time
import unicodedata

import numpy as np
import pandas as pd

import bpv
import nba_data

RECENT_GAMES = 5
MINUTES_CHANGE_WEIGHT = 0.3       # share of a recent minutes change that carries forward
EFFICIENCY_CHANGE_WEIGHT = 0.1    # share of a recent per-minute (shooting/luck) change that does
ROLE_MIN_GAMES = 10               # games needed before a role change can be detected
ROLE_MIN_JUMP = 8                 # last-5 minutes this far above the season average...
ROLE_MAX_PRIOR_MPG = 24           # ...for a player who averaged at most this many minutes
NEW_ROLE_HAIRCUT = 0.9            # per-minute production keeps 90% at the bigger workload
NEW_ROLE_WEIGHT = 0.6             # weight on the new-role projection vs the previous value
# In season, a regular (20+ mpg, 5+ games) not listed Out with an injury who has missed his team's last
# few games plays less of the rest of the season than his history says (analysis/test_availability3.py:
# better in 4 of 5 seasons by absolute error, 5 of 5 by squared error; same slope every season).
ABSENCE_STREAK_COEF = -0.0242     # availability per consecutive team game missed, up to the cap
ABSENCE_STREAK_INTERCEPT = 0.0075
ABSENCE_STREAK_CAP = 20
ABSENCE_STREAK_MIN_MPG = 20
ABSENCE_STREAK_MIN_GAMES = 5
ABSENCE_STREAK_MIN_LEFT = 10      # tested until ~3 weeks before the end, when end-of-season rest starts
PRIOR_SEASON_K = 8                # games of last season's level blended into early-season production
ROOKIE_K = 10                     # games of the draft-slot baseline blended into a rookie's production
AVAILABILITY_DECAY = 0.5          # each older season counts half as much
AVAILABILITY_K = 123              # games of league-average availability blended into each player's record
HISTORY_SEASONS = 5
LEAGUE_TEAMS = int(os.environ.get("LEAGUE_TEAMS", 10))
ROSTER_SIZE = int(os.environ.get("LEAGUE_ROSTER_SIZE", 13))
REPLACEMENT_RANK = LEAGUE_TEAMS * ROSTER_SIZE
MIN_GAMES_RANKED = 10             # fewer games than this and the player isn't used to set replacement level
REPLACEMENT_POOL_MIN = 400        # until this many have 10+ games (mid-December), last season's level is used
OFFSEASON_AFTER_DAYS = 14         # no games for this long means the season is over
SEASON_GAMES = 82

# Change in FPTS per game from one season to the next, by age during the season just played.
# Fitted on 2022-23..2025-26 (players with 20+ games in both seasons and 15+ minutes per game);
# cut preseason error 4.7% in leave-one-season-out tests and beat Basketball-Reference's SPS.
# Also applied to last season's level in the early-season blend (tested: 1.3% less error).
AGE_CURVE = {"<=21": 2.11, "22-23": 0.28, "24-26": -0.26, "27-29": -1.63, "30-32": -2.53, "33+": -3.74}
AGE_MIN_GAMES = 20
AGE_MIN_MPG = 15

# Between seasons: FPTS/game per minute of rotation competition on next season's roster
# (new teammates' last-season minutes per game, league-average team subtracted). Tested:
# 1.4% less preseason error, same coefficient in all four held-out seasons.
CROWDING_COEF = -0.0177
CROWDING_MIN_PREV_MPG = 10

# In-season: FPTS/game gained per minute per game of a 20+ minute teammate who is out
# long-term (entered in data/overrides.json). Tested only for known long-term absences;
# guessing absences from recent missed games gave no gain, so it isn't automatic.
# Between seasons, an injured player's minutes are instead removed from his team's
# roster crowding (the tested preseason model), so the two are never both applied.
TEAMMATE_OUT_COEF = 0.034
TEAMMATE_OUT_MIN_MPG = 20

# In season, the latest official injury report is read automatically. A regular listed Out with an
# injury plays this share of his team's remaining games on average, by injury type (2021-22..2025-26
# reports; beat both BPV's usual estimate and a serious-only rule, on absolute and squared error).
# Means, not medians, because BPV is an expected value. A teammate boost from serious-injury
# listings (no hindsight) beat current BPV: 0.029 FPTS/g per lost minute.
REPORT_SHARE_PLAYED = {"serious": 0.235, "other": 0.402, "soreness": 0.539, "sprain": 0.534, "strain": 0.580}
REPORT_TEAMMATE_COEF = 0.029

# This week's expected FPTS: production x games this week x games-played share x a factor for his status
# on the latest report that included his team's game, and whether he sat out his team's games in the
# last 3 days ("|sat1"). Fitted on 2021-22..2025-26 (analysis/test_weekly_fix.py): cut weekly error by
# 2.2 FPTS vs the single-latest-report version, better in 5 of 5 seasons. Regulars only (20+ mpg, 10+ games).
WEEK_STATUS_FACTOR = {"not_listed|sat0": 1.053, "not_listed|sat1": 0.491, "available|sat0": 0.995,
                      "available|sat1": 1.194, "probable|sat0": 1.07, "probable|sat1": 0.759,
                      "questionable|sat0": 0.977, "questionable|sat1": 0.8, "doubtful|sat0": 0.992,
                      "doubtful|sat1": 0.708, "out_serious|sat0": 0.347, "out_serious|sat1": 0.079,
                      "out_injury|sat0": 0.657, "out_injury|sat1": 0.322, "out_rest|sat0": 1.057,
                      "out_rest|sat1": 0.469, "out_g_league|sat1": 0.169, "out_personal|sat0": 0.615,
                      "out_personal|sat1": 0.675, "out_suspension|sat0": 0.827, "out_suspension|sat1": 0.803,
                      "out_health_protocols|sat0": 0.457, "out_health_protocols|sat1": 0.609,
                      "out_other|sat0": 1.35, "out_other|sat1": 1.028}

# Rookies before their first NBA game: FPTS/game per preseason minute per game above the average
# rookie from his draft range (2+ preseason games). Tested leave-one-season-out: -0.21 FPTS/game.
ROOKIE_PRESEASON_SLOPE = 0.31

# This week's opponents: weekly value x (1 + 0.69 x (average fantasy points the opponents allow per game,
# relative to the league, minus 1)). Better in 5 of 5 seasons but small (about 0.04 FPTS a week).
WEEK_OPPONENT_COEF = 0.69

# Between seasons, blend with ESPN's preseason projections (analysis/test_espn_totals.py, 2021-22 and
# 2023-24..2025-26): production = 62.5% BPV + 37.5% ESPN per game, and availability from ESPN's projected
# games scaled by 0.86 (ESPN projects too many games, but ranks who will miss time well). On season
# totals this tied BPV's error, beat ESPN's by 80 FPTS, ranked players best (0.686 vs 0.664 BPV and
# 0.671 ESPN). Its draft-simulation wins (3 of 4) came from a design that flattered it; with the other nine teams
# drafting by ESPN it about tied ESPN (analysis/test_ten_team.py). Veterans only (20+ games, 15+ mpg);
# not used in season, when ESPN switches to rest-of-season projections.
ESPN_FPG_WEIGHT = 0.375
ESPN_GAMES_SCALE = 0.86

# Early in a season, availability keeps ESPN's preseason projected games (x 0.86 / 82), fading as his team plays:
# weight 41 / (41 + team games played). Players listed Out keep the injury-report share. Tested on 2021-22 and
# 2023-24..2025-26 (docs/prereg-early-availability.md): squared error of the share played 0.0606 -> 0.0584, interval
# -0.0033 to -0.0011, 4 of 4 seasons, stars not worse; most of the gain in the first two weeks.
EARLY_ESPN_K = 41

# Before a season, when ESPN expects a player to miss (most of) the season (0 projected games, or no projection while
# listed OUT), he is expected to play this many games. The 40 veterans (20+ games, 15+ mpg) ESPN flagged this way in
# 2021-22 and 2023-24..2025-26 played 23 on average (docs/prereg-espn-games-curve.md; Tatum 2025-26: 16, Lillard: 0);
# BPV used to ignore the flag and project ~55-60. Found by the expert-gap decomposition (docs/prereg-ecr-gap.md).
ESPN_OUT_GAMES = 23

# Before a season, a veteran (15+ mpg last season) ESPN doesn't project at all, but doesn't list as out either, keeps his
# history-based availability x this (often an injury ESPN knows about, or a lost role). Such veterans played 0.58-0.62 of
# their team's games vs our 0.70-0.73 estimate; fitted on 2021-22, 2023-24, 2024-25, tested on 2025-26
# (docs/prereg-no-espn-availability.md): error 0.274 -> 0.269, overestimate 0.19 -> 0.09.
NO_ESPN_AVAIL_SCALE = 0.854
NO_ESPN_MIN_MPG = 15

# Between seasons, last season's FPTS/game is replaced by per-minute rates x last season's minutes. Each
# scoring stat's rate uses the last 3 seasons, each game weighted 0.5 ** (days before the new season /
# half-life), padded with `pad` minutes at the league-average rate. Half-lives and pads were fitted per
# stat on 2012-13..2018-19 only (analysis/round10_rates.py; docs/prereg-round10.md). On the four scored
# seasons: -0.10 to -0.12 FPTS/game inside the ESPN blend, better in 4 of 4 and for the preseason top 50;
# but flat to slightly worse in 2020-21 and 2022-23, so the real gain is probably nearer -0.05.
RATE_STATS = {"PTS": (200, 100), "FG3M": (200, 50), "FGA": (200, 50), "FGM": (200, 100), "FTA": (200, 100),
              "FTM": (200, 100), "REB": (365, 50), "AST": (200, 50), "STL": (730, 400), "BLK": (550, 100),
              "TOV": (200, 100)}                     # stat: (half-life in days, pad in minutes)
RATE_HISTORY_SEASONS = 3

# In-season recalibration of rest-of-season production: actual ~ a + b x projection. BPV was
# slightly too extreme (young and low-minute players improve during a season). Tested leave-
# one-season-out: better in 3 of 5 seasons, never worse, pooled -0.07 FPTS/game. Applied to
# players with 10+ games. Part of the gain reflects scoring only players who kept playing.
RECALIBRATION = (2.964, 0.910)
RECALIBRATION_MIN_GAMES = 10

# In season, shooting regresses toward the player's OWN level: + b x (his eFG% to date - his eFG% last
# season, or the league's if he took under 200 shots) x his FGA per game; b = -1.85. Tested on every
# weekly checkpoint 2021-22..2025-26: -0.064 FPTS/game error, better in 4 of 5 seasons, and it also
# improved elite players (a league-average reference passed overall but over-penalized efficient stars).
# Players with 10+ games; not used between seasons (tie).
SHOOTING_REGRESSION = -1.85
SHOOTING_PRIOR_MIN_FGA = 200

# Fantasy playoffs: change in games-played share and FPTS/game in the last 4 weeks, by team
# status (win share two weeks before: bad <= .35, top >= .68) and age (veteran = 28+).
# Regulars (20+ mpg, 30+ games). Tested leave-one-season-out on playoff-window FPTS totals:
# better in all 5 seasons (-2.8 FPTS, interval -4.5 to -1.2) beyond the league-wide drop.
PLAYOFF_SHARE_CHANGE = {"bad_vet": -0.438, "bad_young": -0.244, "middle_vet": -0.083, "middle_young": -0.096,
                        "top_vet": -0.088, "top_young": -0.077}
PLAYOFF_FPTS_RATIO = {"bad_vet": 0.935, "bad_young": 1.14, "middle_vet": 0.96, "middle_young": 1.024,
                      "top_vet": 1.013, "top_young": 0.993}
TEAM_BAD, TEAM_TOP = 0.35, 0.68

# 80% ranges for production (actual FPTS/game minus projection), calibrated out of sample.
RANGE_IN_SEASON = [(10, -5.84, 8.19), (20, -5.66, 7.24), (30, -5.75, 7.55), (45, -5.49, 7.80)]   # (min games, low, high)
RANGE_BETWEEN_SEASONS = (-7.34, 6.21)

# What players produced after coming back, for the injury page (analysis/injury_return.py, 2009-10..2025-26, 20+ mpg
# regulars). Context only: a multiplier built from these did not beat BPV out of sample (docs/prereg-injury-return.md),
# because BPV's recent-form term catches up within about 5 games back.
# (absence in team games: min, max, FPTS/game after return as a share of before, minutes share, returns measured)
RETURN_HISTORY = [(5, 9, 0.979, 0.964, 883), (10, 19, 0.962, 0.947, 367), (20, 39, 0.942, 0.940, 113), (40, None, 0.793, 0.859, 6)]
# Listed Out with an injury (20+ mpg regulars, 2021-22..2025-26 reports, first listing of each spell, 21+ team games
# left): team games then missed in a row, by injury type: (median, mean, 80th percentile, spells). For the injury page.
# Not the same thing as REPORT_SHARE_PLAYED, which is his share of ALL remaining games and so includes the ordinary
# absences every player has later in the season.
REPORT_STREAK = {"other": (2, 4.9, 5, 323), "soreness": (2, 5.3, 6, 717), "sprain": (3, 6.9, 10, 404),
                 "strain": (6, 8.3, 13, 229), "serious": (15, 19.8, 33, 74)}
# Back from a whole missed season: FPTS/game as a share of the last season played plus the age adjustment (51 players).
MISSED_SEASON_SHARE, MISSED_SEASON_PLAYERS = 0.866, 51

OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overrides.json")
# Preseason production (the BPV + ESPN blend) saved before each season, used as the early-season prior
# (tested in analysis/test_round9.py: -0.064 FPTS/game, 3 of 4 seasons, vs last season + age).
# Saved rankings, scored later by analysis/accuracy_tracker.py. The app keeps one preseason snapshot per
# season (replaced until opening night) and one in-season snapshot a week, so the record builds itself.
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "snapshots")
SNAPSHOT_COLUMNS = ["rank", "name", "id", "team", "games", "production", "availability", "bpv", "value_over_replacement",
                    "range_low", "range_high", "playoff_games", "production_note", "injury_note", "rookie", "target_season",
                    "espn_fpg", "espn_games"]
AUTO_SNAPSHOT_DAYS = 7
PRESEASON_PRIOR_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "preseason")
CACHE_SECONDS = 30 * 60

STAT_COLUMNS = ["MIN", "PTS", "REB", "AST", "STL", "BLK", "TOV", "FGM", "FGA", "FTM", "FTA", "FG3M"]


def normalize_name(name):
    text = unicodedata.normalize("NFKD", str(name))
    return "".join(c for c in text if not unicodedata.combining(c)).lower().replace(".", "").strip()


def load_overrides():
    """Manual inputs: known injuries and role changes, keyed by player name."""
    if not os.path.exists(OVERRIDES_PATH):
        return {"injuries": {}, "role_changes": {}}
    with open(OVERRIDES_PATH, encoding="utf-8") as f:
        raw = json.load(f)
    return {section: {normalize_name(k): v for k, v in raw.get(section, {}).items() if not k.startswith("_")}
            for section in ("injuries", "role_changes")}


def _production(g, mode, overrides):
    """Production estimate (FPTS/game) for one player's games this season, plus a note on how."""
    fp, mins = g["FPTS"].to_numpy(float), g["MIN"].to_numpy(float)
    n = len(g)
    season_fp, season_min = fp.mean(), mins.mean()
    recent_fp, recent_min = fp[-RECENT_GAMES:].mean(), mins[-RECENT_GAMES:].mean()
    if mode != "in-season" or n < RECENT_GAMES:
        return season_fp, "season average"

    role = overrides["role_changes"].get(normalize_name(g["PLAYER_NAME"].iloc[-1]))
    if role:
        since = g["GAME_DATE"] >= role["since"]
        if since.any() and (~since).any():
            before = g[~since]
            per_min = before["FPTS"].sum() / max(before["MIN"].sum(), 1)
            new_role = per_min * g.loc[since, "MIN"].mean() * NEW_ROLE_HAIRCUT
            previous = 0.8 * season_fp + 0.2 * recent_fp
            return (1 - NEW_ROLE_WEIGHT) * previous + NEW_ROLE_WEIGHT * new_role, "new role (manual)"

    per_min = season_fp / max(season_min, 1)
    if n >= ROLE_MIN_GAMES and recent_min - season_min >= ROLE_MIN_JUMP and season_min <= ROLE_MAX_PRIOR_MPG:
        previous = 0.8 * season_fp + 0.2 * recent_fp
        new_role = per_min * recent_min * NEW_ROLE_HAIRCUT
        return (1 - NEW_ROLE_WEIGHT) * previous + NEW_ROLE_WEIGHT * new_role, "new role (detected)"

    minutes_change = per_min * (recent_min - season_min)
    efficiency_change = recent_fp - season_fp - minutes_change
    return (season_fp + MINUTES_CHANGE_WEIGHT * minutes_change
            + EFFICIENCY_CHANGE_WEIGHT * efficiency_change), "season + recent form"


def _age_adjustment(ages, pid):
    age = ages.get(pid) if ages is not None else None
    if age is None or pd.isna(age):
        return 0.0, None
    return AGE_CURVE[bpv.age_bucket(age)], age


def _range(games, mode, tested):
    """80% range around production, or None where it wasn't calibrated."""
    if not tested:
        return None
    if mode == "in-season":
        if games < RANGE_IN_SEASON[0][0]:
            return None
        return next((lo, hi) for g, lo, hi in reversed(RANGE_IN_SEASON) if games >= g)
    return RANGE_BETWEEN_SEASONS


def build(today=None):
    """Return (players DataFrame sorted by BPV, meta dict)."""
    live = today is None                     # only a build for today saves the preseason prior
    today = today or datetime.date.today()
    season = nba_data.current_season(today)
    current = nba_data.player_game_logs(season)
    if current.empty:
        production_season, mode = nba_data.previous_season(season), "preseason"
    else:
        production_season = season
        last_game = datetime.date.fromisoformat(current["GAME_DATE"].max())
        mode = "in-season" if (today - last_game).days <= OFFSEASON_AFTER_DAYS else "offseason"
    # The season being projected: the current one in-season, otherwise the next one.
    target_season = production_season if mode == "in-season" else nba_data.season_string(
        nba_data.season_start_year(production_season) + 1)

    first = nba_data.season_start_year(production_season) - HISTORY_SEASONS + 1
    seasons = [nba_data.season_string(y) for y in range(first, nba_data.season_start_year(production_season) + 1)]
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in seasons}
    tg = {s: nba_data.team_game_logs(s) for s in seasons}
    draft = nba_data.draft_history()
    overrides = load_overrides()

    hist = bpv.availability_history(seasons, pg, tg, draft)
    if mode == "in-season":
        hist = _record_missed_last_season(hist, seasons, tg, production_season)
    league_p, league_q = bpv.league_availability(hist)
    avail = bpv.predict_availability(hist, seasons, production_season, AVAILABILITY_DECAY, AVAILABILITY_K, league_p)
    baselines = bpv.rookie_baselines(bpv.rookie_seasons(seasons, pg, draft, hist))
    picks = draft.set_index("PERSON_ID")["OVERALL_PICK"]
    debuts = bpv.debut_ids(seasons, pg, draft)[production_season]
    prev_season = hist[hist["season"] == seasons[-2]].set_index("PLAYER_ID")
    this_season = hist[hist["season"] == production_season].set_index("PLAYER_ID")
    espn, frozen_prior, preseason_prior, fpts_rates, espn_out = {}, {}, {}, {}, set()
    if mode == "in-season":
        frozen_prior = _load_preseason_prior(production_season)
        ages = nba_data.player_ages(seasons[-2]).set_index("PLAYER_ID")["AGE"]
        roster_team, crowding = None, {}
    else:
        ages = nba_data.player_ages(production_season).set_index("PLAYER_ID")["AGE"]
        out_share = {normalize_name(name): (1.0 if inj.get("out_for_season")
                                            else min(int(inj.get("out_games", 0)), SEASON_GAMES) / SEASON_GAMES)
                     for name, inj in overrides["injuries"].items()}
        roster_team, crowding = _roster_crowding(pg[production_season], target_season, out_share)
        # Last season's players, players back from a missed season (they played the season before), and the new
        # draftees (no games yet), so returners and incoming rookies get ESPN's projection too.
        name_of = lambda games: games.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
        names = name_of(pg[production_season])
        returning = name_of(pg[seasons[-2]])
        draftees = draft[draft["SEASON"].astype(int) == nba_data.season_start_year(target_season)]
        draftees = draftees.drop_duplicates("PERSON_ID").set_index("PERSON_ID")["PLAYER_NAME"]
        names = pd.concat([names, returning[~returning.index.isin(names.index)]])
        espn_names = pd.concat([names, draftees[~draftees.index.isin(names.index)]])
        espn = _espn_by_player(espn_names, target_season)
        espn_out = _espn_out(espn_names, target_season)
        fpts_rates = _fpts_rates(pg, seasons, target_season)

    last_games = dict(tuple(pg[seasons[-2]].groupby("PLAYER_ID")))
    older_games = dict(tuple(pg[seasons[-3]].groupby("PLAYER_ID"))) if len(seasons) >= 3 else {}

    def recent_games(pid):
        """(games, label): last season if he played 20+ games, else the last two seasons pooled if that makes 20+."""
        last, older = last_games.get(pid), older_games.get(pid)
        if last is not None and len(last) >= AGE_MIN_GAMES:
            return last, seasons[-2]
        parts = [x for x in (older, last) if x is not None]
        pooled = pd.concat(parts) if parts else None
        if pooled is not None and len(pooled) >= AGE_MIN_GAMES:
            return pooled, (f"{seasons[-3]} and {seasons[-2]}" if last is not None and older is not None
                            else seasons[-3] if older is not None else seasons[-2])
        return None, None

    if mode == "in-season":
        # Ages for players who missed last season come from the season before, a year older.
        try:
            older_ages = nba_data.player_ages(seasons[-3]).set_index("PLAYER_ID")["AGE"] + 1
            ages = pd.concat([ages, older_ages[~older_ages.index.isin(ages.index)]])
        except Exception:
            pass

    season_games = pg[production_season]
    league_efg = (season_games["FGM"].sum() + 0.5 * season_games["FG3M"].sum()) / max(season_games["FGA"].sum(), 1)
    last = pg[seasons[-2]].groupby("PLAYER_ID")[["FGM", "FG3M", "FGA"]].sum()
    last = last[last["FGA"] >= SHOOTING_PRIOR_MIN_FGA]
    prior_efg = ((last["FGM"] + 0.5 * last["FG3M"]) / last["FGA"]).to_dict()
    rows = []
    for pid, g in pg[production_season].groupby("PLAYER_ID"):
        g = g.sort_values("GAME_DATE")
        n = len(g)
        mpg = g["MIN"].mean()
        production, note = _production(g, mode, overrides)
        tested_range, use_espn = True, False
        if mode == "in-season":
            if pid in debuts:
                prior = baselines.get(bpv.pick_bucket(picks.get(pid)), baselines["undrafted"])["fpts_per_game"]
                production = bpv.shrink(production, n, prior, ROOKIE_K)
                note += ", blended with draft-slot baseline" if n < 3 * ROOKIE_K else ""
            elif pid in frozen_prior:
                production = bpv.shrink(production, n, frozen_prior[pid], PRIOR_SEASON_K)
                note += ", blended with his preseason projection" if n < 3 * PRIOR_SEASON_K else ""
            elif pid in prev_season.index and prev_season.loc[pid, "played"] >= 20:
                prior = prev_season.loc[pid, "fpts_pg"]
                if prev_season.loc[pid, "mpg"] >= AGE_MIN_MPG:
                    prior += _age_adjustment(ages, pid)[0]
                production = bpv.shrink(production, n, prior, PRIOR_SEASON_K)
                note += ", blended with last season (age-adjusted)" if n < 3 * PRIOR_SEASON_K else ""
            elif recent_games(pid)[0] is not None:
                # Under 20 games last season and no saved projection: the last two seasons pooled as the prior
                # (docs/prereg-short-history.md, T3: error 4.97 -> 4.22 FPTS/game, 11 of 15 seasons).
                g_prior, label = recent_games(pid)
                prior = g_prior["FPTS"].mean()
                if g_prior["MIN"].mean() >= AGE_MIN_MPG:
                    prior += _age_adjustment(ages, pid)[0]
                production = bpv.shrink(production, n, prior, PRIOR_SEASON_K)
                note += f", blended with {label} (age-adjusted)" if n < 3 * PRIOR_SEASON_K else ""
            else:
                # Little NBA history and no saved projection (e.g. a two-way player called up): blend toward the
                # draft-slot baseline, as for rookies (prereg-short-history.md, T2b: 5.55 -> 4.74, 14 of 15 seasons).
                prior = baselines.get(bpv.pick_bucket(picks.get(pid)), baselines["undrafted"])["fpts_per_game"]
                production = bpv.shrink(production, n, prior, ROOKIE_K)
                note += ", blended with draft-slot baseline (little NBA history)" if n < 3 * ROOKIE_K else ""
            if n >= RECALIBRATION_MIN_GAMES:
                production = RECALIBRATION[0] + RECALIBRATION[1] * production
                fga = g["FGA"].sum()
                if fga > 0:
                    player_efg = (g["FGM"].sum() + 0.5 * g["FG3M"].sum()) / fga
                    reference = prior_efg.get(pid, league_efg)
                    production += SHOOTING_REGRESSION * (player_efg - reference) * fga / n
        else:
            tested_range = n >= AGE_MIN_GAMES and mpg >= AGE_MIN_MPG
            if tested_range:
                # Projecting next season: per-stat rates x minutes, then age, then competition for minutes.
                if pid in fpts_rates:
                    production = fpts_rates[pid] * mpg
                adjustment, age = _age_adjustment(ages, pid)
                crowd = CROWDING_COEF * crowding[pid] if pid in crowding else 0.0
                production += adjustment + crowd
                parts = [f"{adjustment:+.1f} for age {age:.0f}" if age is not None else None,
                         f"{crowd:+.1f} for roster competition" if pid in crowding else None]
                base = "per-stat rates (3 seasons) x last season's minutes" if pid in fpts_rates else "last season"
                note = base + (", " + ", ".join(p for p in parts if p) if any(parts) else "")
                if pid in espn:
                    production = (1 - ESPN_FPG_WEIGHT) * production + ESPN_FPG_WEIGHT * espn[pid][0]
                    note += f"; blended {ESPN_FPG_WEIGHT:.0%} with ESPN's projection ({espn[pid][0]:.1f})"
                    preseason_prior[pid] = production
                    use_espn = True
            elif n < AGE_MIN_GAMES and pid in last_games and n + len(last_games[pid]) >= AGE_MIN_GAMES:
                # Under 20 games last season (an injury, usually): his last two seasons pooled, age-adjusted, and the
                # ESPN blend (prereg-short-history.md, T1: 6.50 -> 5.32 FPTS/game vs his short season, 14 of 15
                # seasons; the season before alone was worse than pooling).
                pooled = pd.concat([last_games[pid], g])
                production = pooled["FPTS"].mean()
                note = f"only {n} games in {production_season}: {seasons[-2]} and {production_season} pooled"
                if pooled["MIN"].mean() >= AGE_MIN_MPG:
                    adjustment, age = _age_adjustment(ages, pid)
                    production += adjustment
                    note += f", {adjustment:+.1f} for age {age:.0f}" if age is not None else ""
                if pid in espn:
                    production = (1 - ESPN_FPG_WEIGHT) * production + ESPN_FPG_WEIGHT * espn[pid][0]
                    note += f"; blended {ESPN_FPG_WEIGHT:.0%} with ESPN's projection ({espn[pid][0]:.1f})"
                    preseason_prior[pid] = production
                    use_espn = True
            elif n < AGE_MIN_GAMES:
                # Under 20 games even over two seasons: blend toward the draft-slot baseline, as in season
                # (prereg-short-history.md, T2a: 6.86 -> 5.57 FPTS/game, 15 of 15 seasons).
                prior = baselines.get(bpv.pick_bucket(picks.get(pid)), baselines["undrafted"])["fpts_per_game"]
                production = bpv.shrink(production, n, prior, ROOKIE_K)
                note = f"only {n} NBA games last season: blended with the draft-slot baseline"
        means = g[STAT_COLUMNS].mean()
        # Split the last-5 change into its minutes part and its per-minute (efficiency) part.
        per_min = g["FPTS"].mean() / max(mpg, 1)
        minutes_change = per_min * (g["MIN"].tail(RECENT_GAMES).mean() - mpg)
        efficiency_change = g["FPTS"].tail(RECENT_GAMES).mean() - g["FPTS"].mean() - minutes_change
        # Early in a season (under ROLE_MIN_GAMES), the same split against last season instead of the last 5 games, for
        # players with 20+ games last season. Checked on 2023-24 to 2025-26: after 2 games, 41% of a minutes change
        # carried through the rest of the season (76% of big ones kept their direction), a per-minute change only 11%.
        early = {}
        if mode == "in-season" and n < ROLE_MIN_GAMES and pid in last_games and len(last_games[pid]) >= AGE_MIN_GAMES:
            lg = last_games[pid]
            last_mpg, last_per_min = lg["MIN"].mean(), lg["FPTS"].sum() / max(lg["MIN"].sum(), 1)
            early = {"last_season_minutes": float(last_mpg), "last_season_fpts": float(lg["FPTS"].mean()),
                     "early_minutes_change_fpts": float(last_per_min * (mpg - last_mpg)),
                     "early_efficiency_change_fpts": float(g["FPTS"].mean() - last_per_min * mpg)}
        season_row = this_season.loc[pid] if pid in this_season.index else None
        team = g["TEAM_ABBREVIATION"].iloc[-1]
        if roster_team is not None:
            team = roster_team.get(pid, "FA")
        rows.append({
            "id": int(pid), "name": g["PLAYER_NAME"].iloc[-1], "team": team,
            "games": n, "minutes": float(mpg), "season_fpts": float(g["FPTS"].mean()),
            "recent_fpts": float(g["FPTS"].tail(RECENT_GAMES).mean()),
            "recent_minutes": float(g["MIN"].tail(RECENT_GAMES).mean()),
            "minutes_change_fpts": float(minutes_change), "efficiency_change_fpts": float(efficiency_change), **early,
            "production": float(production), "production_note": note,
            "range": _range(n, mode, tested_range),
            "availability": (min(1.0, ESPN_GAMES_SCALE * espn[pid][1] / SEASON_GAMES) if use_espn
                             else float(avail.get(pid, league_p))),
            "espn_fpg": espn[pid][0] if pid in espn else None, "espn_games": espn[pid][1] if pid in espn else None,
            "games_missed": int(season_row["missed"]) if season_row is not None else 0,
            "games_missed_long": int(season_row["missed_long"]) if season_row is not None else 0,
            # Before a season, everyone listed here has NBA games; the rookies are the "projection only" rows below.
            "rookie": bool(pid in debuts) if mode == "in-season" else False,
            "per_game": {c: float(means[c]) for c in STAT_COLUMNS},
            "last_games": g.tail(RECENT_GAMES)[["GAME_DATE", "MATCHUP", "MIN", "FPTS"]].iloc[::-1]
                           .to_dict(orient="records"),
        })

    # Players on a roster with no games in the production season but 20+ games the season before.
    # Between seasons (e.g. a torn Achilles): start from that season, age-adjusted, with the usual ESPN blend; they are
    # saved in the preseason prior like everyone else. Not backtested: no test covered players returning from a full
    # missed season. In season (everyone who hasn't played yet, which early on is most of the league): the saved
    # preseason projection if there is one, else last season's average; regulars lose availability for each team game
    # missed so far, as in _absence_streaks (that rule was tested on regulars who had already played this season).
    listed = {r["id"] for r in rows}
    try:
        roster_now = nba_data.rosters(target_season).set_index("PLAYER_ID")["TEAM_ABBREVIATION"]
    except Exception:
        roster_now = pd.Series(dtype=object)
    rostered = set(roster_now.index)
    if mode == "in-season":
        ages_before = ages
        team_played = tg[production_season].groupby("TEAM_ABBREVIATION").size()
        candidates = [(pid, *recent_games(pid)) for pid in sorted(rostered - listed)]
        candidates = [c for c in candidates if c[1] is not None]
    else:
        before = pg[seasons[-2]]
        before = before[before["PLAYER_ID"].isin(rostered - listed)]
        try:
            ages_before = nba_data.player_ages(seasons[-2]).set_index("PLAYER_ID")["AGE"] + 1 if len(before) else None
        except Exception:       # e.g. offline without that file: skip the age adjustment rather than the ratings
            ages_before = None
        candidates = [(pid, g, seasons[-2]) for pid, g in before.groupby("PLAYER_ID") if len(g) >= AGE_MIN_GAMES]
    for pid, g, label in candidates:
        n, mpg = len(g), g["MIN"].mean()
        team = roster_now.get(pid, g["TEAM_ABBREVIATION"].iloc[-1])
        production = g["FPTS"].mean()
        note = (f"no games yet this season: {label} average" if mode == "in-season"
                else f"missed all of {production_season}: {label} average")
        if mpg >= AGE_MIN_MPG:
            adjustment, age = _age_adjustment(ages_before, pid)
            production += adjustment
            note += f", {adjustment:+.1f} for age {age:.0f}" if age is not None else ""
        availability = float(avail.get(pid, league_p))
        if mode == "in-season" and pid in frozen_prior:
            production = float(frozen_prior[pid])
            note = "no games yet this season: his preseason projection"
        if mode == "in-season" and mpg >= ABSENCE_STREAK_MIN_MPG:
            missed = int(team_played.get(team, 0))
            if missed:
                availability = min(1.0, max(0.0, availability + ABSENCE_STREAK_INTERCEPT
                                            + ABSENCE_STREAK_COEF * min(missed, ABSENCE_STREAK_CAP)))
                note += f"; has missed his team's first {missed} game{'s' if missed > 1 else ''}"
        if pid in espn:
            production = (1 - ESPN_FPG_WEIGHT) * production + ESPN_FPG_WEIGHT * espn[pid][0]
            availability = min(1.0, ESPN_GAMES_SCALE * espn[pid][1] / SEASON_GAMES)
            note += f"; blended {ESPN_FPG_WEIGHT:.0%} with ESPN's projection ({espn[pid][0]:.1f})"
            preseason_prior[pid] = production
        rows.append({
            "id": int(pid), "name": g["PLAYER_NAME"].iloc[-1], "team": team, "games": 0, "minutes": None,
            "season_fpts": None, "recent_fpts": None, "recent_minutes": None,
            "minutes_change_fpts": None, "efficiency_change_fpts": None,
            "production": float(production), "production_note": note,
            "range": None, "availability": availability,
            "espn_fpg": espn[pid][0] if pid in espn else None, "espn_games": espn[pid][1] if pid in espn else None,
            "games_missed": 0, "games_missed_long": 0, "rookie": False,
            "per_game": None, "last_games": [],
        })

    # Drafted players with no NBA games yet (upcoming rookies, or rookies who haven't debuted).
    listed = {r["id"] for r in rows}
    upcoming_year = nba_data.season_start_year(target_season)
    rookie_pre = _rookie_preseason(seasons, draft, target_season)
    for d in draft[draft["SEASON"].astype(int) == upcoming_year].itertuples():
        if d.PERSON_ID in listed:
            continue
        base = baselines.get(bpv.pick_bucket(d.OVERALL_PICK), baselines["undrafted"])
        team = roster_team.get(d.PERSON_ID, d.TEAM_ABBREVIATION) if roster_team is not None else d.TEAM_ABBREVIATION
        production = base["fpts_per_game"]
        note = f"projection only: average rookie from picks {bpv.pick_bucket(d.OVERALL_PICK)}"
        adj = rookie_pre(d.PERSON_ID, bpv.pick_bucket(d.OVERALL_PICK))
        if adj is not None:
            production += adj
            note += f", {adj:+.1f} for preseason minutes"
        # Same ESPN blend as veterans, games included (docs/prereg-rookie-espn.md: -82 season FPTS of error).
        availability, espn_row = league_p, espn.get(d.PERSON_ID)
        if espn_row is not None:
            production = (1 - ESPN_FPG_WEIGHT) * production + ESPN_FPG_WEIGHT * espn_row[0]
            availability = min(1.0, ESPN_GAMES_SCALE * espn_row[1] / SEASON_GAMES)
            note += f"; blended {ESPN_FPG_WEIGHT:.0%} with ESPN's projection ({espn_row[0]:.1f})"
            preseason_prior[d.PERSON_ID] = production
        if mode == "in-season" and d.PERSON_ID in frozen_prior:
            # Hasn't played yet: his preseason projection (with ESPN's blend) rather than the bare draft-slot average.
            production = float(frozen_prior[d.PERSON_ID])
            note = "no games yet: his preseason projection"
        rows.append({
            "id": int(d.PERSON_ID), "name": d.PLAYER_NAME, "team": team, "games": 0, "minutes": None,
            "season_fpts": None, "recent_fpts": None, "recent_minutes": None,
            "minutes_change_fpts": None, "efficiency_change_fpts": None,
            "production": production, "production_note": note,
            "range": None, "availability": availability,
            "espn_fpg": espn_row[0] if espn_row else None, "espn_games": espn_row[1] if espn_row else None,
            "games_missed": 0, "games_missed_long": 0, "rookie": True,
            "per_game": None, "last_games": [],
        })

    # ESPN expects him to miss (most of) the season: availability from ESPN_OUT_GAMES instead of his history.
    for r in rows:
        if r["id"] in espn_out:
            r["availability"] = ESPN_OUT_GAMES / SEASON_GAMES
            r["production_note"] += "; ESPN expects him to miss most of the season"
    no_espn = set()
    if mode != "in-season":
        for r in rows:
            if (r["espn_games"] is None and r["id"] not in espn_out and not r["rookie"]
                    and (r["minutes"] or 0) >= NO_ESPN_MIN_MPG):
                r["availability"] *= NO_ESPN_AVAIL_SCALE
                r["production_note"] += "; no ESPN projection (check injury news)"
                no_espn.add(r["id"])
    if mode != "in-season" and live and not _season_started(target_season):
        _save_preseason_prior(target_season, preseason_prior)
        # The early-season fade turns saved games into availability (x ESPN_GAMES_SCALE), so out players are saved
        # at the games that give ESPN_OUT_GAMES.
        saved_games = {int(r["id"]): r["espn_games"] for r in rows if r.get("espn_games")}
        saved_games.update({int(r["id"]): ESPN_OUT_GAMES / ESPN_GAMES_SCALE for r in rows if r["id"] in espn_out})
        # ...and the scaled-down availability of veterans ESPN doesn't project, so it carries into the early-season fade.
        saved_games.update({int(r["id"]): r["availability"] * SEASON_GAMES / ESPN_GAMES_SCALE for r in rows if r["id"] in no_espn})
        _save_preseason_espn_games(target_season, saved_games)
    df = pd.DataFrame(rows)
    ranked = df[df["games"] >= MIN_GAMES_RANKED]
    if len(ranked) >= max(REPLACEMENT_POOL_MIN, REPLACEMENT_RANK + 100):
        replacement = bpv.replacement_level(ranked["production"], REPLACEMENT_RANK)
    else:
        # Early in a season the 10+ game pool is incomplete (the 130th best of ~200 players is far too low: 20.6 on
        # 2025-11-12 vs 26 before and after): use last season's level, as analysis/backtest.py does.
        prev = hist[(hist["season"] == seasons[-2]) & (hist["played"] >= 20)]
        replacement = bpv.replacement_level(prev["fpts_pg"], REPLACEMENT_RANK)
    df["manageable"] = league_q
    df["injury_note"] = ""
    df.loc[df["id"].isin(no_espn), "injury_note"] = "no ESPN projection: check injury news"

    # Games left for each team (in-season), for known injuries.
    team_games_played = tg[production_season].groupby("TEAM_ABBREVIATION").size() if mode == "in-season" else None

    def remaining_games(team):
        return SEASON_GAMES - (int(team_games_played.get(team, 0)) if team_games_played is not None else 0)

    # The latest official injury report (in season): status, chance of playing, serious injuries.
    report_rows = _latest_report_by_player(df) if mode == "in-season" else {}
    df["report_status"] = [report_rows.get(i, {}).get("status") for i in df.index]
    df["report_reason"] = [report_rows.get(i, {}).get("reason") for i in df.index]
    df["play_probability"] = [bpv.PLAY_PROBABILITY.get(st) if st else None for st in df["report_status"]]
    # ESPN's average draft position: how most fantasy players value him (the suggestions page's "would they accept").
    df["adp"] = _espn_adp(df["name"], target_season)

    # Known injuries: the injured player's value, and a boost for his teammates' production.
    # Manual entries (data/overrides.json) come first; then injuries on the official report, by type.
    injured, lost_minutes = {}, {}
    for i, r in df.iterrows():
        injury = overrides["injuries"].get(normalize_name(r["name"]))
        remaining = remaining_games(r.team)
        if injury:
            out = remaining if injury.get("out_for_season") else min(int(injury.get("out_games", 0)), remaining)
            note = "out for the season" if injury.get("out_for_season") else f"out {out} more games"
            coef = TEAMMATE_OUT_COEF
        elif (r.report_status == "Out" and bpv.absence_reason(r.report_reason) == "injury"
              and bpv.injury_type(r.report_reason) in REPORT_SHARE_PLAYED):
            kind = bpv.injury_type(r.report_reason)
            share = REPORT_SHARE_PLAYED[kind]
            # The share is his expected share of ALL remaining games (it already includes the ordinary absences
            # later on), so it replaces his availability, as tested (analysis/test_availability3.py). Until
            # 2026-10-20 the missing share was IR'd and his normal availability applied on top, counting those
            # absences twice (docs/prereg-report-share.md: -0.05 error in the share played, 5 of 5 seasons).
            streak = min(REPORT_STREAK[kind][1], (1 - share) * remaining)
            note = (f"out (injury report: {r.report_reason}); players listed like this played about {share:.0%} of "
                    f"their team's remaining games, usually after missing about {REPORT_STREAK[kind][0]} in a row")
            # The teammate boost was tested for serious injuries only, using his full minutes.
            if kind == "serious" and r.minutes is not None and not pd.isna(r.minutes) and r.minutes >= TEAMMATE_OUT_MIN_MPG:
                lost_minutes[r.team] = lost_minutes.get(r.team, 0.0) + REPORT_TEAMMATE_COEF * r.minutes
            df.at[i, "availability"] = share
            injured[i] = ("report", remaining, streak, note)
            continue
        else:
            continue
        injured[i] = (remaining, out, note)
        if r.minutes is not None and not pd.isna(r.minutes) and r.minutes >= TEAMMATE_OUT_MIN_MPG and remaining > 0:
            lost_minutes[r.team] = lost_minutes.get(r.team, 0.0) + coef * r.minutes * out / remaining
    for i, r in df.iterrows():
        boost = lost_minutes.get(r.team, 0.0) if mode == "in-season" else 0.0
        if boost and i not in injured and r.games > 0:
            df.at[i, "production"] = r.production + boost
            df.at[i, "production_note"] = f"{r.production_note}, {boost:+.1f} for injured teammates"

    if mode == "in-season":
        _absence_streaks(df, injured, pg[production_season], tg[production_season], remaining_games)
        espn_games = _load_preseason_espn_games(production_season)
        if espn_games:
            team_played = tg[production_season].groupby("TEAM_ABBREVIATION").size()
            for i, r in df.iterrows():
                if r.id in espn_games and r.report_status != "Out":
                    w = EARLY_ESPN_K / (EARLY_ESPN_K + int(team_played.get(r.team, 0)))
                    espn_avail = min(1.0, ESPN_GAMES_SCALE * espn_games[r.id] / SEASON_GAMES)
                    df.at[i, "availability"] = w * espn_avail + (1 - w) * r.availability

    values = []
    for i, r in df.iterrows():
        value = bpv.bpv_value(r.production, r.availability, league_q, replacement)
        if i in injured and injured[i][0] == "report":
            _, remaining, streak, note = injured[i]
            if remaining > 0:
                # BPV's formula with his known stretch counted as IR-able: the typical streak for his injury type
                # is streamed at replacement, the rest of his missed games get the league's usual long-stretch share.
                missed = (1 - r.availability) * remaining
                value = (r.availability * r.production
                         + (streak + max(0.0, missed - streak) * league_q) * replacement / remaining)
            df.at[i, "injury_note"] = note
        elif i in injured:
            remaining, out, note = injured[i]
            if remaining > 0:
                # Manual entries: out games are one long stretch: IR him and stream the replacement.
                value = 0.0 if out == remaining else ((remaining - out) * value + out * replacement) / remaining
            df.at[i, "injury_note"] = note
        values.append(value)
    df["bpv"] = values
    df["value_over_replacement"] = df["bpv"] - replacement
    df["range_low"] = [r[0] + p if r else None for r, p in zip(df["range"], df["production"])]
    df["range_high"] = [r[1] + p if r else None for r, p in zip(df["range"], df["production"])]
    df = df.drop(columns=["range"])

    try:
        target_schedule = nba_data.schedule(target_season)
        playoffs = bpv.playoff_games(target_schedule)
    except Exception:
        target_schedule, playoffs = None, {}
    df["playoff_games"] = [playoffs.get(t) for t in df["team"]]
    df["playoff_fpts"] = _playoff_fpts(df, mode, tg[production_season], target_schedule, ages, today)
    df["week_games"], df["week_fpts"] = _this_week(df, mode, tg[production_season], target_schedule, today,
                                                   pg[production_season])

    df = df.sort_values("bpv", ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    df["heat_check_index"] = (100 * df["bpv"] / df["bpv"].max()).clip(lower=0).astype(int)

    meta = {
        "season": production_season, "target_season": target_season, "mode": mode,
        "replacement_level": replacement, "league_teams": LEAGUE_TEAMS, "roster_size": ROSTER_SIZE,
        "league_availability": league_p, "manageable_share": league_q,
        "playoff_games_range": [min(playoffs.values()), max(playoffs.values())] if playoffs else None,
        "rookie_baselines": baselines, "history_seasons": seasons,
        "updated": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    if live and (mode == "in-season" or not _season_started(target_season)):
        _auto_snapshot(df, mode, target_season, today)
    return df, meta


OPENING_TIP_HOUR_ET = 12         # opening night 2026-27 had a game finished by 6 PM Eastern; noon to be safe


def _season_started(target_season):
    """True once the season's first game may have tipped, even if no box score is out yet. Before that, the preseason
    snapshot and prior are rewritten on every build; after it, they must stay frozen (a late run on opening night would
    otherwise save a "preseason" ranking made with that night's news)."""
    try:
        opener = nba_data.schedule(target_season)["GAME_DATE"].min()
    except Exception:
        return False
    utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    now_et = utc - datetime.timedelta(hours=4 if 3 <= utc.month <= 11 else 5)
    today_et = now_et.date().isoformat()
    return today_et > opener or (today_et == opener and now_et.hour >= OPENING_TIP_HOUR_ET)


def _auto_snapshot(df, mode, target_season, today):
    """Keep the snapshot record up to date: the latest preseason ranking, then one a week in season."""
    save_snapshot(df.assign(target_season=target_season)[SNAPSHOT_COLUMNS], "bpv", mode, target_season, today)


def save_snapshot(out, prefix, mode, target_season, today):
    """Save <prefix>_<date>_pre_<season>.csv before the season (replacing older ones for that season),
    or <prefix>_<date>_auto.csv in season if none was saved in the last week. Returns the path or None."""
    try:
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        if mode != "in-season":
            # Only the last preseason ranking before opening night matters.
            name = f"{prefix}_{today.isoformat()}_pre_{target_season}.csv"
            for old in os.listdir(SNAPSHOT_DIR):
                if old.startswith(prefix + "_") and old.endswith(f"_pre_{target_season}.csv") and old != name:
                    os.remove(os.path.join(SNAPSHOT_DIR, old))
            path = os.path.join(SNAPSHOT_DIR, name)
            out.to_csv(path, index=False)
            return path
        start = today - datetime.timedelta(days=AUTO_SNAPSHOT_DAYS)
        for f in os.listdir(SNAPSHOT_DIR):
            m = re.match(prefix + r"_(\d{4}-\d{2}-\d{2})", f)
            if m and "_pre_" not in f and start < datetime.date.fromisoformat(m.group(1)) <= today:
                return None
        path = os.path.join(SNAPSHOT_DIR, f"{prefix}_{today.isoformat()}_auto.csv")
        out.to_csv(path, index=False)
        return path
    except OSError:
        return None


def _espn_key(name):
    n = normalize_name(name).replace("-", " ").replace("'", "")
    for suffix in (" jr", " sr", " ii", " iii", " iv"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return " ".join(n.split())


def _absence_streaks(df, injured, season_games, team_games, remaining_games):
    """Lower availability for regulars who have missed their team's last few games (not listed Out injured)."""
    last_played = season_games.groupby("PLAYER_ID")["GAME_DATE"].max()
    dates = team_games.groupby("TEAM_ABBREVIATION")["GAME_DATE"].apply(list)
    for i, r in df.iterrows():
        if (i in injured or r.games < ABSENCE_STREAK_MIN_GAMES or not r.minutes or r.minutes < ABSENCE_STREAK_MIN_MPG
                or remaining_games(r.team) < ABSENCE_STREAK_MIN_LEFT):
            continue
        last = last_played.get(r.id)
        if last is None or r.team not in dates.index:
            continue
        streak = sum(d > last for d in dates[r.team])
        new = min(1.0, max(0.0, r.availability + ABSENCE_STREAK_INTERCEPT
                           + ABSENCE_STREAK_COEF * min(streak, ABSENCE_STREAK_CAP)))
        df.at[i, "availability"] = new
        if streak >= 1:
            df.at[i, "injury_note"] = f"has missed his team's last {streak} game{'s' if streak > 1 else ''}"


def _record_missed_last_season(hist, seasons, tg, season):
    """In season, record a rostered regular (20+ mpg two seasons ago) who missed all of last season as missing it,
    as bpv.availability_history does once he plays again. Without this his availability would be the healthy-looking
    older record until his first game, and then drop."""
    try:
        rostered = set(nba_data.rosters(season)["PLAYER_ID"])
    except Exception:
        return hist
    last, before = seasons[-2], seasons[-3]
    seen_last = set(hist.loc[hist["season"] == last, "PLAYER_ID"])
    rel = hist[(hist["season"] == before) & (hist["mpg"] >= bpv.RELEVANT_MPG) & hist["PLAYER_ID"].isin(rostered)
               & ~hist["PLAYER_ID"].isin(seen_last)]
    if rel.empty:
        return hist
    n = int(tg[last].groupby("TEAM_ID").size().median())
    extra = pd.DataFrame({"PLAYER_ID": rel["PLAYER_ID"].to_numpy(), "PLAYER_NAME": rel["PLAYER_NAME"].to_numpy(),
                          "played": 0, "missed": n, "missed_long": n, "spells": 1, "possible": n, "mpg": 0.0,
                          "fpts_pg": np.nan, "fpts_total": 0.0, "availability": 0.0, "manageable": 1.0, "season": last})
    return pd.concat([hist, extra], ignore_index=True)


def _save_preseason_prior(target_season, prior):
    """Save the BPV + ESPN preseason production; rewritten on each build until the season starts."""
    if not prior:
        return
    try:
        os.makedirs(PRESEASON_PRIOR_DIR, exist_ok=True)
        pd.Series(prior, name="production").rename_axis("PLAYER_ID").to_csv(
            os.path.join(PRESEASON_PRIOR_DIR, f"prior_{target_season}.csv"))
    except OSError:
        pass


def _save_preseason_espn_games(target_season, games):
    """Save ESPN's preseason projected games (ESPN switches to rest-of-season projections once games start)."""
    if not games:
        return
    try:
        os.makedirs(PRESEASON_PRIOR_DIR, exist_ok=True)
        pd.Series(games, name="espn_games").rename_axis("PLAYER_ID").to_csv(
            os.path.join(PRESEASON_PRIOR_DIR, f"espn_games_{target_season}.csv"))
    except OSError:
        pass


def _load_preseason_espn_games(season):
    """player id -> ESPN's preseason projected games for this season, or {} if none were saved."""
    path = os.path.join(PRESEASON_PRIOR_DIR, f"espn_games_{season}.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["PLAYER_ID"], df["espn_games"]))


def _load_preseason_prior(season):
    """player id -> saved preseason production for this season, or {} if none was saved."""
    path = os.path.join(PRESEASON_PRIOR_DIR, f"prior_{season}.csv")
    if not os.path.exists(path):
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["PLAYER_ID"], df["production"]))


def _fpts_rates(pg, seasons, target_season):
    """player id -> projected FPTS per minute from decay-weighted, padded per-stat rates (see RATE_STATS)."""
    start = pd.Timestamp(f"{nba_data.season_start_year(target_season)}-10-21")      # about opening night
    games = pd.concat([pg[s] for s in seasons[-RATE_HISTORY_SEASONS:]])
    days = (start - pd.to_datetime(games["GAME_DATE"])).dt.days.to_numpy(float)
    league = pg[seasons[-1]]
    total = None
    for stat, (half_life, pad) in RATE_STATS.items():
        w = 0.5 ** (days / half_life)
        sums = pd.DataFrame({"PLAYER_ID": games["PLAYER_ID"].to_numpy(), "s": games[stat].to_numpy(float) * w,
                             "m": games["MIN"].to_numpy(float) * w}).groupby("PLAYER_ID").sum()
        league_rate = league[stat].sum() / league["MIN"].sum()
        rate = (sums["s"] + pad * league_rate) / (sums["m"] + pad) * bpv.SCORING[stat]
        total = rate if total is None else total + rate
    return total.dropna().to_dict()


def _espn_out(names, target_season):
    """Player ids ESPN expects to miss (most of) the season (see ESPN_OUT_GAMES), or an empty set."""
    try:
        proj = nba_data.espn_projections(target_season)
    except Exception:
        return set()
    if proj is None or proj.empty:
        return set()
    out = proj["ESPN_OUT"].astype(bool) if "ESPN_OUT" in proj else proj["ESPN_GP"].fillna(-1).eq(0)
    keys = {_espn_key(n) for n in proj.loc[out, "PLAYER_NAME"]}
    return {pid for pid, n in names.items() if _espn_key(n) in keys}


def _espn_adp(names, target_season):
    """ESPN average draft position per row of `names` (NaN when unknown or undrafted)."""
    try:
        own = nba_data.espn_ownership(target_season)
    except Exception:
        return [np.nan] * len(names)
    if own is None or own.empty:
        return [np.nan] * len(names)
    by_key = {_espn_key(n): a for n, a in zip(own["PLAYER_NAME"], own["ADP"])}
    return [by_key.get(_espn_key(n), np.nan) for n in names]


def _espn_by_player(names, target_season):
    """player id -> (ESPN projected FPTS/game, ESPN projected games), or {} if unavailable. names: id -> name."""
    try:
        proj = nba_data.espn_projections(target_season)
    except Exception:
        return {}
    if proj is None or proj.empty:
        return {}
    by_key = {_espn_key(n): (float(f), float(g)) for n, f, g in zip(proj.PLAYER_NAME, proj.ESPN_FPG, proj.ESPN_GP) if g > 0}
    return {pid: by_key[_espn_key(n)] for pid, n in names.items() if _espn_key(n) in by_key}


def _rookie_preseason(seasons, draft, target_season):
    """Function (player id, pick bucket) -> FPTS/game adjustment from preseason minutes, or None."""
    try:
        pre_now = nba_data.preseason_game_logs(target_season).groupby("PLAYER_ID")["MIN"].agg(["size", "mean"])
    except Exception:
        return lambda pid, bucket: None
    if pre_now.empty:
        return lambda pid, bucket: None
    # Average preseason minutes of past rookies by draft range (2+ preseason games).
    rows = []
    for s in seasons[1:]:
        try:
            pre = nba_data.preseason_game_logs(s).groupby("PLAYER_ID")["MIN"].agg(["size", "mean"])
        except Exception:
            continue
        year = nba_data.season_start_year(s)
        for d in draft[draft["SEASON"].astype(int) == year].itertuples():
            if d.PERSON_ID in pre.index and pre.loc[d.PERSON_ID, "size"] >= 2:
                rows.append((bpv.pick_bucket(d.OVERALL_PICK), pre.loc[d.PERSON_ID, "mean"]))
    typical = pd.DataFrame(rows, columns=["bucket", "mpg"]).groupby("bucket")["mpg"].mean() if rows else pd.Series(dtype=float)

    def adjust(pid, bucket):
        if pid not in pre_now.index or pre_now.loc[pid, "size"] < 2 or bucket not in typical.index:
            return None
        return ROOKIE_PRESEASON_SLOPE * (pre_now.loc[pid, "mean"] - typical[bucket])
    return adjust


def _latest_report_by_player(df):
    """Row index -> {"status", "reason"}: each player's status on the latest official injury report that
    included his team's game (reports list only teams playing that day). Empty if unavailable."""
    try:
        reports = nba_data.recent_injury_reports()
    except Exception:
        return {}
    if reports is None or reports.empty:
        return {}
    team_latest = {}
    for report_date, matchup in zip(reports["REPORT_DATE"], reports["Matchup"]):
        for team in str(matchup).split("@"):
            team_latest[team] = max(team_latest.get(team, ""), report_date)
    status = {}
    for report_date, n, st, reason in zip(reports["REPORT_DATE"], reports["Player Name"],
                                          reports["Current Status"], reports["Reason"]):
        status[(normalize_name(bpv.report_player_name(n)), report_date)] = (st, reason)
    out = {}
    for i, r in df.iterrows():
        report_date = team_latest.get(r.team)
        hit = status.get((normalize_name(r["name"]), report_date)) if report_date else None
        if hit:
            out[i] = {"status": hit[0], "reason": hit[1]}
    return out


def _week_status(status, reason):
    if not status:
        return "not_listed"
    if status != "Out":
        return status.lower()
    category = bpv.absence_reason(reason)
    if category == "injury":
        return "out_serious" if bpv.SERIOUS_INJURY.search(str(reason)) else "out_injury"
    return f"out_{category}"


def _this_week(df, mode, team_games, schedule, today, player_games=None):
    """(games left this Monday-Sunday week, expected FPTS in them), in season only."""
    if mode != "in-season" or schedule is None:
        return [None] * len(df), [None] * len(df)
    since = (today - datetime.timedelta(days=3)).isoformat()
    teams_recent = set(team_games[team_games["GAME_DATE"] >= since]["TEAM_ABBREVIATION"])
    played_recent = set(player_games[player_games["GAME_DATE"] >= since]["PLAYER_ID"]) if player_games is not None else set()
    sunday = today + datetime.timedelta(days=6 - today.weekday())
    left = schedule[(schedule["GAME_DATE"] >= today.isoformat()) & (schedule["GAME_DATE"] <= sunday.isoformat())]
    games_left = left.groupby("TEAM_ABBREVIATION").size()
    played = team_games.groupby("TEAM_ABBREVIATION").size()
    # Fantasy points allowed per game by each team so far (relative to the league average).
    allowed = {}
    if player_games is not None and "MATCHUP" in team_games:
        opp = team_games.assign(OPP=team_games["MATCHUP"].str[-3:])[["GAME_ID", "TEAM_ID", "OPP"]]
        fp = player_games.merge(opp, on=["GAME_ID", "TEAM_ID"]).groupby(["OPP", "GAME_ID"])["FPTS"].sum()
        per_team = fp.groupby("OPP").mean()
        allowed = (per_team / per_team.mean()).to_dict()
    opp_strength = {}
    if "OPPONENT" in left:
        for team, grp in left.groupby("TEAM_ABBREVIATION"):
            opp_strength[team] = float(np.mean([allowed.get(o, 1.0) for o in grp["OPPONENT"]])) - 1
    weeks, values = [], []
    for r in df.itertuples():
        g = int(games_left.get(r.team, 0))
        weeks.append(g)
        if r.games < 10 or (r.minutes or 0) < 20:
            values.append(None)
            continue
        share = min(r.games / max(played.get(r.team, r.games), 1), 1.0)
        sat = r.team in teams_recent and r.id not in played_recent
        key = f"{_week_status(r.report_status, r.report_reason)}|sat{int(sat)}"
        factor = WEEK_STATUS_FACTOR.get(key, 1.0)
        values.append(float(r.production * g * share * factor * (1 + WEEK_OPPONENT_COEF * opp_strength.get(r.team, 0.0))))
    return weeks, values


def _playoff_fpts(df, mode, team_games, schedule, ages, today):
    """Expected fantasy-playoff FPTS: production x expected games played in the playoff window.

    In season, the team's status (bad / middle / top) comes from its record two weeks before the
    window, or its record so far if that date hasn't arrived. Between seasons, status is unknown,
    so the league-wide late-season change for middle teams is used.
    """
    if schedule is None:
        return [None] * len(df)
    start, _ = bpv.playoff_window(schedule["GAME_DATE"].max())
    status = {}
    if mode == "in-season":
        cut = (datetime.date.fromisoformat(start) - datetime.timedelta(days=14)).isoformat()
        rec = team_games[team_games["GAME_DATE"] < min(cut, today.isoformat())]
        win_share = rec.groupby("TEAM_ABBREVIATION")["WL"].apply(lambda x: (x == "W").mean())
        status = {t: "bad" if w <= TEAM_BAD else "top" if w >= TEAM_TOP else "middle" for t, w in win_share.items()}
        played = team_games.groupby("TEAM_ABBREVIATION").size()
    out = []
    for r in df.itertuples():
        games = r.playoff_games
        if games is None or pd.isna(games) or r.games < 30 or (r.minutes or 0) < 20:
            out.append(None)
            continue
        age = ages.get(r.id) if ages is not None else None
        group = f"{status.get(r.team, 'middle')}_{'vet' if age is not None and age >= 28 else 'young'}"
        share = r.games / max(played.get(r.team, r.games), 1) if mode == "in-season" else r.availability
        share = min(max(share + PLAYOFF_SHARE_CHANGE[group], 0), 1)
        out.append(float(r.production * PLAYOFF_FPTS_RATIO[group] * share * games))
    return out


def _roster_crowding(season_games, target_season, out_share=None):
    """(team by player id, crowding by player id) for next season's rosters.

    Crowding = last-season minutes per game of his new teammates who played 10+ mpg,
    minus the league-average team total (as in analysis/test_minutes_model.py).
    Teammates marked injured count only for the share of the season they'll play.
    """
    try:
        rosters = nba_data.rosters(target_season)
    except Exception:
        return {}, {}
    team_of = rosters.set_index("PLAYER_ID")["TEAM_ABBREVIATION"]
    prev_mpg = season_games.groupby("PLAYER_ID")["MIN"].mean()
    contrib = prev_mpg.reindex(team_of.index).fillna(0)
    contrib = contrib.where(contrib >= CROWDING_MIN_PREV_MPG, 0)
    if out_share:
        names = rosters.set_index("PLAYER_ID")["PLAYER_NAME"].map(normalize_name)
        contrib = contrib * (1 - names.map(out_share).fillna(0))
    team_total = contrib.groupby(team_of).sum()
    crowding = team_of.map(team_total) - contrib - team_total.mean()
    return team_of.to_dict(), crowding.to_dict()


REPORT_STATUSES = ["Out", "Doubtful", "Questionable", "Probable"]


def _return_history(games_out):
    """What players back from an absence this long produced, or None."""
    for lo, hi, fpts, minutes, n in RETURN_HISTORY:
        if games_out >= lo and (hi is None or games_out <= hi):
            return {"absence": f"{lo}-{hi}" if hi else f"{lo}+", "fpts_share": fpts, "minutes_share": minutes, "returns": n}
    return None


def injury_list(df, meta):
    """Everyone on the latest official injury report for his team (Out, Doubtful, Questionable, Probable), plus,
    between seasons, players coming back from a whole missed season. Each listed player gets his BPV, chance of
    playing, how many games in a row players Out with that kind of injury went on to miss (REPORT_STREAK) and what
    players back from absences that long produced (RETURN_HISTORY, context only)."""
    try:
        reports = nba_data.recent_injury_reports()
    except Exception:
        reports = None
    by_name = {normalize_name(n): i for i, n in zip(df.index, df["name"])}
    try:
        played = nba_data.team_game_logs(meta["season"]).groupby("TEAM_ABBREVIATION").size()             if meta.get("mode") == "in-season" else pd.Series(dtype=int)
    except Exception:
        played = pd.Series(dtype=int)
    out, report_date = [], None
    if reports is not None and not reports.empty:
        reports = reports[reports["Current Status"].isin(REPORT_STATUSES)]
        team_latest = {}
        for d, matchup in zip(reports["REPORT_DATE"], reports["Matchup"]):
            for team in str(matchup).split("@"):
                team_latest[team] = max(team_latest.get(team, ""), d)
        report_date = max(team_latest.values()) if team_latest else None
        seen = set()
        for r in reports.sort_values("REPORT_DATE", ascending=False).itertuples(index=False):
            name = bpv.report_player_name(r[reports.columns.get_loc("Player Name")])
            key = normalize_name(name)
            if key in seen:
                continue
            i = by_name.get(key)
            p = df.loc[i] if i is not None else None
            teams = str(r.Matchup).split("@")
            team = p["team"] if p is not None and p["team"] in teams else None
            # Only his team's latest report counts (reports list only the teams playing that day).
            latest = team_latest.get(team) if team else max(team_latest.get(t, "") for t in teams)
            if r.REPORT_DATE != latest:
                continue
            seen.add(key)
            status, reason = r[reports.columns.get_loc("Current Status")], str(r.Reason)
            category = bpv.absence_reason(reason)
            kind = bpv.injury_type(reason) if category == "injury" else None
            row = {"name": p["name"] if p is not None else name, "id": int(p["id"]) if p is not None else None,
                   "team": team or str(r.Team), "status": status, "reason": reason, "category": category,
                   "injury_type": kind, "report_date": r.REPORT_DATE, "game_date": str(r[reports.columns.get_loc("Game Date")]),
                   "matchup": str(r.Matchup), "play_probability": bpv.PLAY_PROBABILITY.get(status),
                   "rank": int(p["rank"]) if p is not None else None, "bpv": float(p["bpv"]) if p is not None else None,
                   "production": float(p["production"]) if p is not None else None,
                   "streak": None, "share_played": None, "return_history": None}
            if status == "Out" and category == "injury" and kind in REPORT_STREAK:
                median, mean, p80, n = REPORT_STREAK[kind]
                remaining = SEASON_GAMES - int(played.get(team, 0)) if team else SEASON_GAMES
                row["streak"] = {"median": min(median, remaining), "mean": min(mean, remaining), "p80": min(p80, remaining),
                                 "spells": n}
                row["return_history"] = _return_history(round(mean))
                row["share_played"] = REPORT_SHARE_PLAYED.get(kind)
            out.append(row)
    order = {s: k for k, s in enumerate(REPORT_STATUSES)}
    out.sort(key=lambda x: (order.get(x["status"], 9), x["rank"] or 10 ** 6))
    returning = []
    if meta.get("mode") != "in-season":
        back = df[(df["games"] == 0) & df["production_note"].str.startswith("missed all of")]
        for _, p in back.iterrows():
            returning.append({"name": p["name"], "id": int(p["id"]), "team": p["team"], "rank": int(p["rank"]),
                              "bpv": float(p["bpv"]), "production": float(p["production"]), "note": p["production_note"]})
    return {"report_date": report_date, "players": out, "returning": returning,
            "missed_season_history": {"fpts_share": MISSED_SEASON_SHARE, "players": MISSED_SEASON_PLAYERS},
            "return_history": [{"absence": f"{lo}-{hi}" if hi else f"{lo}+", "fpts_share": f, "minutes_share": m, "returns": n}
                               for lo, hi, f, m, n in RETURN_HISTORY]}


# Curry mode (2026-10-20, a joke, "just for right now"). Display only: applied to what the site serves through get(),
# never to snapshots, accuracy scoring, the preseason prior or refresh.py's in-season checks (they use get_real()).
# Set to False to turn it off.
CURRY_MODE = False
CURRY_BPV = 203.0           # comfortably ahead of everyone (Jokic is ~53)


def apply_jokes(df):
    """Steph Curry #1 by a comical margin. Returns df unchanged when CURRY_MODE is off or he isn't listed."""
    if not CURRY_MODE or "name" not in df:
        return df
    hit = df["name"] == "Stephen Curry"
    if not hit.any():
        return df
    df = df.copy()
    if "joke_note" not in df:
        df["joke_note"] = None
    i = df.index[hit][0]
    real_bpv, real_rank = float(df.at[i, "bpv"]), int(df.at[i, "rank"])
    replacement = float(df.at[i, "bpv"] - df.at[i, "value_over_replacement"])
    df.at[i, "bpv"] = CURRY_BPV
    df.at[i, "production"] = 210.0
    df.at[i, "availability"] = 1.0
    df.at[i, "value_over_replacement"] = CURRY_BPV - replacement
    df.at[i, "range_low"], df.at[i, "range_high"] = 195.0, 230.0
    df.at[i, "joke_note"] = (f"Night night. The model refuses to project a ceiling. (Joke mode: his real BPV is "
                             f"{real_bpv:.1f}, #{real_rank}.)")
    top = df[~hit].sort_values("bpv", ascending=False).index[0]
    df.at[top, "joke_note"] = "Still the best player in the world who isn't Stephen Curry."
    df = df.sort_values("bpv", ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    df["heat_check_index"] = (100 * df["bpv"] / df["bpv"].max()).clip(lower=0).astype(int)
    return df


_cache = {"at": 0, "day": None, "value": None}
_cache_lock = threading.Lock()


def get():
    """Cached (players, meta) as the site shows them (apply_jokes on top of get_real())."""
    players, meta = get_real()
    return apply_jokes(players), meta


def get_real():
    """Cached (players, meta).

    Offline (the live site) the data only changes on a deploy, so the ratings are rebuilt only when the date changes
    (for the date-based values such as this week's games): at most once a day. Online they're rebuilt after
    CACHE_SECONDS, as the data behind them refreshes. No background threads (a threaded server hung on Render).
    """
    with _cache_lock:
        today = datetime.date.today()
        stale = (_cache["day"] != today) if nba_data.OFFLINE else (time.time() - _cache["at"] > CACHE_SECONDS)
        if _cache["value"] is None or stale:
            _cache.update(value=build(), at=time.time(), day=today)
        return _cache["value"]


def version():
    """When the cached ratings were built (changes after every rebuild)."""
    return _cache["at"]
