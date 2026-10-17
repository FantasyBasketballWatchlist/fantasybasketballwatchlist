"""Availability, round 2: fairer scoring, rare lost seasons, and more candidate factors.

Run after test_availability.py:  python -m analysis.test_availability2   (writes analysis/test_availability2.json)

Availability enters BPV as an expected value, so squared error is scored alongside absolute error.
Also checked: whether a factor helps flag lost seasons (availability under 50%), by rank AUC.
New candidates:
  B1 playoff minutes last season (deep runs, short summers)
  B2 share of games missed in the second half of last season
  B3 his team's win % last season (bad teams sit veterans)
  B4 years since being drafted
  B5 everything together (rounds 1 and 2, rows with no report-based features)
Same rule: 95% interval excludes 0 in favor AND better in most held-out seasons.
"""
import json
import os
import warnings

import numpy as np
import pandas as pd
from nba_api.stats.endpoints import LeagueGameLog

from analysis import backtest as bt
from analysis import test_availability as ta
from analysis import test_misc as tm
import nba_data

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_availability2.json")


def playoff_minutes(season):
    def fetch():
        return LeagueGameLog(season=season, player_or_team_abbreviation="P", season_type_all_star="Playoffs",
                             league_id="00", timeout=nba_data.REQUEST_TIMEOUT).get_data_frames()[0]
    df = nba_data._cached(f"playoff_player_games_{season}", fetch, False)
    return df.groupby("PLAYER_ID").MIN.sum()


def second_half_missed(pg, tg, season):
    g = pg[season]
    t = tg[season]
    mid = t.GAME_DATE.sort_values().iloc[len(t) // 2]
    played = g[g.GAME_DATE >= mid].groupby("PLAYER_ID").size()
    team = g.sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
    team_n = t[t.GAME_DATE >= mid].groupby("TEAM_ID").size()
    return (1 - played.reindex(team.index).fillna(0) / team.map(team_n)).clip(0, 1)


def add_features(d, pg, tg):
    draft = nba_data.draft_history().drop_duplicates("PERSON_ID", keep="last").set_index("PERSON_ID")
    d = d.copy()
    for col in ("playoff_min", "second_half_missed", "team_win", "experience"):
        d[col] = np.nan
    for t in d.target.unique():
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        m = d.target == t
        pm = playoff_minutes(prev) / 100
        d.loc[m, "playoff_min"] = d.loc[m, "PLAYER_ID"].map(pm).fillna(0)
        d.loc[m, "second_half_missed"] = d.loc[m, "PLAYER_ID"].map(second_half_missed(pg, tg, prev))
        win = tg[prev].groupby("TEAM_ID").WL.apply(lambda x: (x == "W").mean())
        team = pg[prev].sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
        d.loc[m, "team_win"] = d.loc[m, "PLAYER_ID"].map(team.map(win))
        year = nba_data.season_start_year(prev)
        d.loc[m, "experience"] = d.loc[m, "PLAYER_ID"].map(year - draft.SEASON.astype(int))
    return d


def judge_both(d, new, old):
    d = d.reset_index(drop=True)
    d["key"] = d.PLAYER_ID.astype(str) + d.target
    out = {}
    for name, loss in (("abs", lambda x: np.abs(x)), ("squared", lambda x: x ** 2)):
        b = tm.boot(d, loss(d[new] - d.availability), loss(d[old] - d.availability), key="key")
        per = {s: float((loss(g[new] - g.availability) - loss(g[old] - g.availability)).mean()) for s, g in d.groupby("target")}
        wins = sum(v < 0 for v in per.values())
        v = tm.verdict(b)
        out[name] = {"minus_base": b, "seasons_better": f"{wins}/{len(per)}",
                     "verdict": "better" if v == "better" and wins > len(per) / 2 else ("tie" if v == "better" else v)}
    lost = d.availability < 0.5
    if lost.any() and (~lost).any():
        out["lost_season_auc"] = {"base": _auc(-d[old], lost), "new": _auc(-d[new], lost), "lost_seasons": int(lost.sum())}
    return out


def _auc(score, label):
    r = pd.Series(np.asarray(score)).rank()
    label = np.asarray(label)
    n1, n0 = label.sum(), (~label).sum()
    return float((r[label].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def evaluate(d, base, feats):
    scored, coefs = ta.correct(d, base, feats)
    rec = ta.recenter(scored, base)
    return {"features": feats, "n": len(rec), "coefs_by_fold": coefs, **judge_both(rec, "new", "recentered")}


ROUND1 = ["age", "mpg", "total_min", "trail", "spells", "trend", "weight", "height", "usage"]
CANDIDATES = {
    "B1_playoff_minutes": ["playoff_min"], "B2_second_half_missed": ["second_half_missed"],
    "B3_team_win_pct": ["team_win"], "B4_experience": ["experience"],
    "B5_everything": ROUND1 + ["playoff_min", "second_half_missed", "team_win", "experience"],
}
CANDIDATES.update({f"R1_{k}": v for k, v in ta.CANDIDATES.items()})


def main():
    pg, tg = bt.load()
    d = pd.read_csv(os.path.join(nba_data.CACHE_DIR, "availability_features.csv"))
    d = add_features(d, pg, tg)
    res = {}
    for base in ("p_hat", "espn"):
        res[base] = {}
        for name, feats in CANDIDATES.items():
            r = evaluate(d.dropna(subset=[base]), base, feats)
            res[base][name] = r
            print(base, name, "| abs", r["abs"]["verdict"], round(r["abs"]["minus_base"]["diff"], 5), r["abs"]["seasons_better"],
                  "| sq", r["squared"]["verdict"], round(r["squared"]["minus_base"]["diff"], 5), r["squared"]["seasons_better"],
                  "| AUC", {k: round(v, 3) for k, v in r.get("lost_season_auc", {}).items()}, flush=True)
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
