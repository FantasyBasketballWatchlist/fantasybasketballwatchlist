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
# 0.671 ESPN) and won 3 of 4 seasons of draft simulations. Veterans only (20+ games, 15+ mpg);
# not used in season, when ESPN switches to rest-of-season projections.
ESPN_FPG_WEIGHT = 0.375
ESPN_GAMES_SCALE = 0.86

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

OVERRIDES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overrides.json")
# Preseason production (the BPV + ESPN blend) saved before each season, used as the early-season prior
# (tested in analysis/test_round9.py: -0.064 FPTS/game, 3 of 4 seasons, vs last season + age).
# Saved rankings, scored later by analysis/accuracy_tracker.py. The app keeps one preseason snapshot per
# season (replaced until opening night) and one in-season snapshot a week, so the record builds itself.
SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "snapshots")
SNAPSHOT_COLUMNS = ["rank", "name", "id", "team", "games", "production", "availability", "bpv", "value_over_replacement",
                    "range_low", "range_high", "playoff_games", "production_note", "injury_note", "rookie", "target_season"]
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
    league_p, league_q = bpv.league_availability(hist)
    avail = bpv.predict_availability(hist, seasons, production_season, AVAILABILITY_DECAY, AVAILABILITY_K, league_p)
    baselines = bpv.rookie_baselines(bpv.rookie_seasons(seasons, pg, draft, hist))
    picks = draft.set_index("PERSON_ID")["OVERALL_PICK"]
    debuts = bpv.debut_ids(seasons, pg, draft)[production_season]
    prev_season = hist[hist["season"] == seasons[-2]].set_index("PLAYER_ID")
    this_season = hist[hist["season"] == production_season].set_index("PLAYER_ID")
    espn, frozen_prior, preseason_prior, fpts_rates = {}, {}, {}, {}
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
        # Last season's players, plus the new draftees (no games yet) so incoming rookies get ESPN's projection too.
        names = pg[production_season].drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
        draftees = draft[draft["SEASON"].astype(int) == nba_data.season_start_year(target_season)]
        draftees = draftees.drop_duplicates("PERSON_ID").set_index("PERSON_ID")["PLAYER_NAME"]
        espn = _espn_by_player(pd.concat([names, draftees[~draftees.index.isin(names.index)]]), target_season)
        fpts_rates = _fpts_rates(pg, seasons, target_season)

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
        tested_range = True
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
        means = g[STAT_COLUMNS].mean()
        # Split the last-5 change into its minutes part and its per-minute (efficiency) part.
        per_min = g["FPTS"].mean() / max(mpg, 1)
        minutes_change = per_min * (g["MIN"].tail(RECENT_GAMES).mean() - mpg)
        efficiency_change = g["FPTS"].tail(RECENT_GAMES).mean() - g["FPTS"].mean() - minutes_change
        season_row = this_season.loc[pid] if pid in this_season.index else None
        team = g["TEAM_ABBREVIATION"].iloc[-1]
        if roster_team is not None:
            team = roster_team.get(pid, "FA")
        rows.append({
            "id": int(pid), "name": g["PLAYER_NAME"].iloc[-1], "team": team,
            "games": n, "minutes": float(mpg), "season_fpts": float(g["FPTS"].mean()),
            "recent_fpts": float(g["FPTS"].tail(RECENT_GAMES).mean()),
            "recent_minutes": float(g["MIN"].tail(RECENT_GAMES).mean()),
            "minutes_change_fpts": float(minutes_change), "efficiency_change_fpts": float(efficiency_change),
            "production": float(production), "production_note": note,
            "range": _range(n, mode, tested_range),
            "availability": (min(1.0, ESPN_GAMES_SCALE * espn[pid][1] / SEASON_GAMES) if (tested_range and pid in espn)
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

    # Players on a roster who missed all of the production season (e.g. a torn Achilles) but played 20+ games the
    # season before: start from that season, age-adjusted, with the usual ESPN blend before a season.
    # Not backtested: no test covered players returning from a full missed season.
    listed = {r["id"] for r in rows}
    try:
        rostered = set(nba_data.rosters(target_season)["PLAYER_ID"])
    except Exception:
        rostered = set()
    before = pg[seasons[-2]]
    before = before[before["PLAYER_ID"].isin(rostered - listed)]
    try:
        ages_before = nba_data.player_ages(seasons[-2]).set_index("PLAYER_ID")["AGE"] + 1 if len(before) else None
    except Exception:       # e.g. offline without that file: skip the age adjustment rather than the ratings
        ages_before = None
    for pid, g in before.groupby("PLAYER_ID"):
        n, mpg = len(g), g["MIN"].mean()
        if n < AGE_MIN_GAMES:
            continue
        production = g["FPTS"].mean()
        note = f"missed all of {production_season}: {seasons[-2]} average"
        if mpg >= AGE_MIN_MPG:
            adjustment, age = _age_adjustment(ages_before, pid)
            production += adjustment
            note += f", {adjustment:+.1f} for age {age:.0f}" if age is not None else ""
        availability = float(avail.get(pid, league_p))
        if pid in espn:
            production = (1 - ESPN_FPG_WEIGHT) * production + ESPN_FPG_WEIGHT * espn[pid][0]
            availability = min(1.0, ESPN_GAMES_SCALE * espn[pid][1] / SEASON_GAMES)
            note += f"; blended {ESPN_FPG_WEIGHT:.0%} with ESPN's projection ({espn[pid][0]:.1f})"
        team = roster_team.get(pid, "FA") if roster_team is not None else g["TEAM_ABBREVIATION"].iloc[-1]
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

    if mode != "in-season" and live:
        _save_preseason_prior(target_season, preseason_prior)
    df = pd.DataFrame(rows)
    ranked = df[df["games"] >= MIN_GAMES_RANKED]
    replacement = bpv.replacement_level(ranked["production"], REPLACEMENT_RANK)
    df["manageable"] = league_q
    df["injury_note"] = ""

    # Games left for each team (in-season), for known injuries.
    team_games_played = tg[production_season].groupby("TEAM_ABBREVIATION").size() if mode == "in-season" else None

    def remaining_games(team):
        return SEASON_GAMES - (int(team_games_played.get(team, 0)) if team_games_played is not None else 0)

    # The latest official injury report (in season): status, chance of playing, serious injuries.
    report_rows = _latest_report_by_player(df) if mode == "in-season" else {}
    df["report_status"] = [report_rows.get(i, {}).get("status") for i in df.index]
    df["report_reason"] = [report_rows.get(i, {}).get("reason") for i in df.index]
    df["play_probability"] = [bpv.PLAY_PROBABILITY.get(st) if st else None for st in df["report_status"]]

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
            out = round((1 - share) * remaining)
            note = f"expected to play about {share:.0%} of remaining games ({kind}; injury report: {r.report_reason})"
            # The teammate boost was tested for serious injuries only, using his full minutes.
            if kind == "serious" and r.minutes is not None and not pd.isna(r.minutes) and r.minutes >= TEAMMATE_OUT_MIN_MPG:
                lost_minutes[r.team] = lost_minutes.get(r.team, 0.0) + REPORT_TEAMMATE_COEF * r.minutes
            injured[i] = (remaining, out, note)
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

    values = []
    for i, r in df.iterrows():
        value = bpv.bpv_value(r.production, r.availability, league_q, replacement)
        if i in injured:
            remaining, out, note = injured[i]
            if remaining > 0:
                # Out games are one long stretch: IR him and stream the replacement.
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
    if live:
        _auto_snapshot(df, mode, target_season, today)
    return df, meta


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
            df.at[i, "injury_note"] = (f"has missed his team's last {streak} game{'s' if streak > 1 else ''}; "
                                       f"availability lowered to {new:.0%}")


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


_cache = {"at": 0, "value": None}
_cache_lock = threading.Lock()


def get():
    """Cached (players, meta)."""
    with _cache_lock:
        if _cache["value"] is None or time.time() - _cache["at"] > CACHE_SECONDS:
            _cache["value"] = build()
            _cache["at"] = time.time()
        return _cache["value"]
