"""Ten-team league: nine preseason models and ESPN, each drafting for one team.

Run:  python -m analysis.test_ten_team        (writes analysis/test_ten_team.json)

Seasons with genuine ESPN preseason projections: 2021-22, 2023-24, 2024-25, 2025-26.
Pool: everyone with 20+ games last season who played again (retirements dropped, as in backtest.py).
Every team takes the best player left on its own list; a list's unranked players come after all its
ranked ones. Teams are scored by their 13 players' actual season FPTS, and by their best 10 (only 10
start in a standard ESPN league, so bench points are worth little).

Design A ("one of each"): the 10 lists get one team each; the seats are shuffled for each of 1,000 drafts.
  Caution: several models are near-copies (M3/M5, the BPV variants). Similar lists take the same players,
  so they cut into each other and flatter lists that are different from the rest, such as ESPN.
Design B ("you vs an ESPN league"): one team drafts by the model, the other nine by ESPN's projections.
  Every draft is deterministic, so all 10 seats are run exactly; the score is the model team's FPTS minus
  what an ESPN-drafting team got from the same seat. This is the cleaner test of "should I use this list?".

The hybrid uses the app's constants (37.5% ESPN per game, ESPN games x 0.86), which were chosen on these
same four seasons, so it has an in-sample advantage here. The other models' pieces (age curve, crowding,
availability) come from seasons before the one being drafted.
"""
import itertools
import json
import math
import os
import random
import warnings
from collections import defaultdict

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_espn_projections as te_
from analysis import test_minutes_model as tmm
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_ten_team.json")
TEAMS, ROUNDS, STARTERS, SIMS = 10, 13, 10, 1000
ESPN = "ESPN projections"
MODELS = ["M1 season FPTS/game", "M2 80/20", "M3 x career GP%", "M5 80/20 x career GP%", "Last season total FPTS",
          "BPV (replacement-level)", "BPV + age", "BPV + age + crowding", "BPV + ESPN hybrid (app)"]


def season_frame(pg, tg, hist, league_p, league_q, t, names):
    df, R = bt.preseason_frame(pg, hist, t, ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K, league_p, league_q,
                               age_curve=bt.age_curve_before(pg, t))
    df = df.rename(columns={"M1 season FPTS": "M1 season FPTS/game"})
    # Production behind "BPV + age" (bpv_value is linear in production), then the app's later preseason pieces.
    age_prod = (df["BPV + age"] - (1 - df.p_hat) * league_q * R) / df.p_hat
    crowd = tmm.roster_context(pg, t).crowding.reindex(df.index).fillna(0)
    prev_mpg = hist[hist.season == bt.SEASONS[bt.SEASONS.index(t) - 1]].set_index("PLAYER_ID").mpg.reindex(df.index)
    prod = age_prod + ratings.CROWDING_COEF * crowd.where(prev_mpg >= ratings.CROWDING_MIN_PREV_MPG, 0)
    df["BPV + age + crowding"] = bpv.bpv_value(prod, df.p_hat, league_q, R)

    espn = te_.projections(te_.ESPN_SEASONS[t])
    espn["PLAYER_ID"] = espn.name.map(te_.key).map(names)
    espn = espn.dropna(subset=["PLAYER_ID"]).drop_duplicates("PLAYER_ID").set_index("PLAYER_ID")
    e_fpg, e_gp, e_tot = (espn[c].reindex(df.index) for c in ("espn_fpg", "espn_gp", "espn_total"))
    team_games = int(tg[t].groupby("TEAM_ID").size().median())
    veteran = (prev_mpg >= 15) & e_fpg.notna() & (e_gp > 0)
    h_prod = prod.where(~veteran, (1 - ratings.ESPN_FPG_WEIGHT) * prod + ratings.ESPN_FPG_WEIGHT * e_fpg)
    h_p = df.p_hat.where(~veteran, (e_gp * ratings.ESPN_GAMES_SCALE / team_games).clip(0, 1))
    df["BPV + ESPN hybrid (app)"] = bpv.bpv_value(h_prod, h_p, league_q, R)
    df[ESPN] = e_tot
    for c in MODELS + [ESPN]:
        df[c] = df[c].fillna(-math.inf)
    return df


def run_draft(order, rankings, taken_init=frozenset()):
    """order: list of 10 list names by seat. Returns seat -> roster (player ids)."""
    taken, rosters, ptr = set(taken_init), defaultdict(list), {s: 0 for s in set(order)}
    for rnd in range(ROUNDS):
        for seat in (range(TEAMS) if rnd % 2 == 0 else range(TEAMS - 1, -1, -1)):
            ranking = rankings[order[seat]]
            i = ptr[order[seat]]
            while ranking[i] in taken:
                i += 1
            ptr[order[seat]] = i
            taken.add(ranking[i])
            rosters[seat].append(ranking[i])
    return rosters


def team_scores(roster, actual):
    vals = sorted((actual[p] for p in roster), reverse=True)
    return sum(vals), sum(vals[:STARTERS])


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    lists = MODELS + [ESPN]
    res = {"design_A": {}, "design_B": {}, "pool": {}}
    for t in te_.ESPN_SEASONS:
        df = season_frame(pg, tg, hist, league_p, league_q, t, names)
        actual = df.actual_total.to_dict()
        rankings = {c: df[c].sort_values(ascending=False, kind="stable").index.tolist() for c in lists}
        res["pool"][t] = {"players": len(df), "with_espn_projection": int(np.isfinite(df[ESPN]).sum())}

        # Design A
        rng = random.Random(7)
        tot, top = defaultdict(list), defaultdict(list)
        wins = defaultdict(int)
        for _ in range(SIMS):
            order = lists[:]
            rng.shuffle(order)
            rosters = run_draft(order, rankings)
            best = None
            for seat, roster in rosters.items():
                a, b = team_scores(roster, actual)
                tot[order[seat]].append(a)
                top[order[seat]].append(b)
                if best is None or b > best[1]:
                    best = (order[seat], b)
            wins[best[0]] += 1
        res["design_A"][t] = {c: {"total13": float(np.mean(tot[c])), "best10": float(np.mean(top[c])),
                                  "league_wins_best10": wins[c] / SIMS} for c in lists}

        # Design B: seat s drafts by the list, the others by ESPN; compared with an all-ESPN league.
        base = run_draft([ESPN] * TEAMS, rankings)
        base_scores = {s: team_scores(base[s], actual) for s in range(TEAMS)}
        block = {}
        for c in lists:
            d13, d10, beat = [], [], 0
            for s in range(TEAMS):
                order = [ESPN] * TEAMS
                order[s] = c
                rosters = run_draft(order, rankings)
                a, b = team_scores(rosters[s], actual)
                d13.append(a - base_scores[s][0])
                d10.append(b - base_scores[s][1])
                others = [team_scores(rosters[o], actual)[1] for o in range(TEAMS) if o != s]
                beat += sum(b > x for x in others) / (TEAMS - 1)
            block[c] = {"gain_total13": float(np.mean(d13)), "gain_best10": float(np.mean(d10)),
                        "seats_better_best10": int(sum(x > 0 for x in d10)),
                        "share_of_espn_teams_beaten_best10": beat / TEAMS}
        res["design_B"][t] = block
        print(t, "done", flush=True)

    seasons = list(te_.ESPN_SEASONS)
    res["summary_A"] = {c: {"best10_mean": float(np.mean([res["design_A"][t][c]["best10"] for t in seasons])),
                            "league_win_rate": float(np.mean([res["design_A"][t][c]["league_wins_best10"] for t in seasons])),
                            "seasons_top_best10": sum(max(res["design_A"][t], key=lambda k: res["design_A"][t][k]["best10"]) == c
                                                      for t in seasons)} for c in lists}
    res["summary_B"] = {c: {"gain_best10_mean": float(np.mean([res["design_B"][t][c]["gain_best10"] for t in seasons])),
                            "gain_total13_mean": float(np.mean([res["design_B"][t][c]["gain_total13"] for t in seasons])),
                            "seasons_gain_positive": sum(res["design_B"][t][c]["gain_best10"] > 0 for t in seasons),
                            "espn_teams_beaten": float(np.mean([res["design_B"][t][c]["share_of_espn_teams_beaten_best10"] for t in seasons]))}
                        for c in lists}
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(json.dumps({"pool": res["pool"], "summary_A": res["summary_A"], "summary_B": res["summary_B"]}, indent=1))


if __name__ == "__main__":
    main()
