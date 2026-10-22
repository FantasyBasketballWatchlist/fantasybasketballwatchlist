"""Rebuild the app's in-season BPV as of any date of a past season (only games and injury reports known by then).

    from analysis.bpv_replay import ratings_on
    players, meta = ratings_on("2024-25", datetime.date(2024, 12, 15))
"""
import datetime
import os

os.environ.setdefault("NBA_OFFLINE", "1")

import pandas as pd   # noqa: E402

import nba_data   # noqa: E402

_orig = {}


def ratings_on(season, day):
    """(players, meta) from ratings.build as of `day` in `season`: game logs cut to games before `day`, the injury
    report published on `day`, and no live sources (ESPN, rosters) for that season."""
    import ratings
    os.environ["NBA_SEASON"] = season
    for name in ("player_game_logs", "team_game_logs", "recent_injury_reports", "rosters", "espn_projections", "schedule"):
        _orig.setdefault(name, getattr(nba_data, name))
    cut = day.isoformat()

    def logs(fn):
        def g(s, *a, **k):
            df = _orig[fn](s, *a, **k)
            return df[df["GAME_DATE"] < cut] if s == season and "GAME_DATE" in df else df
        return g
    nba_data.player_game_logs = logs("player_game_logs")
    nba_data.team_game_logs = logs("team_game_logs")

    def reports(*a, **k):
        rep = _orig_reports(season)
        return rep[rep["REPORT_DATE"] == cut] if len(rep) else rep
    nba_data.recent_injury_reports = reports

    def schedule(s, *a, **k):
        if s != season:
            return _orig["schedule"](s, *a, **k)
        tg = _orig["team_game_logs"](season)              # the season's real schedule, from its game logs
        return pd.DataFrame({"GAME_DATE": tg["GAME_DATE"], "TEAM_ABBREVIATION": tg["TEAM_ABBREVIATION"],
                             "OPPONENT": tg["MATCHUP"].str[-3:], "HOME": tg["MATCHUP"].str.contains("vs.")})
    nba_data.schedule = schedule

    def unavailable(*a, **k):
        raise FileNotFoundError("not available for a replayed season")
    nba_data.rosters = unavailable
    nba_data.espn_projections = unavailable
    try:
        return ratings.build(today=day)
    finally:
        for name, f in _orig.items():
            setattr(nba_data, name, f)
        os.environ.pop("NBA_SEASON", None)


def _orig_reports(season):
    return nba_data.injury_reports(season)
