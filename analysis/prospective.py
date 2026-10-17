"""Prospective 2026-27 test of the three-source blend (docs/prereg-round10.md, item 1).

Freeze today's projections (run again close to opening night to refresh; each run writes a dated file):
    python -m analysis.prospective freeze
Score a frozen file once the season is over:
    python -m analysis.prospective score data/snapshots/prospective_2026-27_<date>.csv

Columns (season totals, ESPN default points; per-game versions end in _fpg):
  base   the app's formula as of the freeze date (BPV + ESPN blend, per-stat rates)
  bpv    BPV alone (no ESPN): own production x own availability x 82
  espn   ESPN's projection: per game x projected games
  ecr    FantasyPros consensus rank turned into points with the curve fitted on 2021-22..2025-26
  blend3 equal-thirds average of bpv, espn and ecr (sources a player lacks are left out)
Decision rule, fixed now: blend3 replaces the base formula for preseason rankings if, on the pool of
players in any source's preseason top 150 (injured players kept), it has lower season-total error
AND higher rank correlation with actual totals than base. One season is weak evidence either way;
the result is added to the four backtest seasons, not judged alone.
"""
import datetime
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import round10 as r10
from analysis import test_espn_projections as te_
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = "2026-27"
SNAP_DIR = os.path.join(ROOT, "data", "snapshots")
RANK_FILE = os.path.join(ROOT, "data", "rankings", f"fp_ecr_{TARGET}.csv")


def ecr_curves():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    frames = pd.concat([r10.season_data(pg, tg, hist, league_p, league_q, t, names, debuts) for t in r10.SEASONS])
    return r10.ecr_curve(frames, "act_total"), r10.ecr_curve(frames, "act_fpg")


def own_availability(meta_season):
    """BPV's own games-played share (without ESPN), as ratings.build computes it before the ESPN swap."""
    last = nba_data.season_start_year(meta_season)
    seasons = [nba_data.season_string(y) for y in range(last - ratings.HISTORY_SEASONS + 1, last + 1)]
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in seasons}
    tg = {s: nba_data.team_game_logs(s) for s in seasons}
    hist = bpv.availability_history(seasons, pg, tg, nba_data.draft_history())
    league_p, _ = bpv.league_availability(hist)
    return bpv.predict_availability(hist, seasons, meta_season, ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K, league_p), league_p


def freeze():
    players, meta = ratings.get()
    assert meta["mode"] != "in-season", "freeze before the season starts"
    p = players.set_index("id")
    w = ratings.ESPN_FPG_WEIGHT
    blended = p.production_note.str.contains("blended", na=False) & p.espn_fpg.notna()
    own_fpg = np.where(blended, (p.production - w * p.espn_fpg.fillna(0)) / (1 - w), p.production)
    avail, league_p = own_availability(meta["season"])
    own_p = avail.reindex(p.index).fillna(league_p)
    tot_curve, fpg_curve = ecr_curves()

    ecr = pd.read_csv(RANK_FILE)
    by_key = {ratings._espn_key(n): r for n, r in zip(ecr["name"], ecr["rank"])}
    rank = p["name"].map(lambda n: by_key.get(ratings._espn_key(n)))
    matched = {ratings._espn_key(n) for n in p["name"]}
    unmatched = [n for n in ecr["name"] if ratings._espn_key(n) not in matched]

    out = pd.DataFrame(index=p.index)
    out["name"] = p["name"]
    out["base_fpg"], out["base"] = p.production, p.production * p.availability * ratings.SEASON_GAMES
    out["bpv_fpg"], out["bpv"] = own_fpg, own_fpg * own_p * ratings.SEASON_GAMES
    out["espn_fpg"], out["espn"] = p.espn_fpg, p.espn_fpg * p.espn_games
    out["ecr_rank"] = rank
    r = rank.to_numpy(float)
    out["ecr_fpg"] = np.where(~np.isnan(r), fpg_curve(r), np.nan)
    out["ecr"] = np.where(~np.isnan(r), tot_curve(r), np.nan)
    out["blend3_fpg"] = r10.weighted(out, ["bpv_fpg", "espn_fpg", "ecr_fpg"], [1, 1, 1])
    out["blend3"] = r10.weighted(out, ["bpv", "espn", "ecr"], [1, 1, 1])
    today = datetime.date.today().isoformat()
    path = os.path.join(SNAP_DIR, f"prospective_{TARGET}_{today}.csv")
    out.reset_index().rename(columns={"index": "id"}).to_csv(path, index=False)
    with open(path.replace(".csv", "_meta.json"), "w") as fh:
        json.dump({"frozen": today, "ratings_updated": meta.get("updated"), "ecr_file": os.path.relpath(RANK_FILE, ROOT),
                   "ecr_unmatched_players (rookies without NBA games, mostly)": unmatched}, fh, indent=1)
    print(f"wrote {path}: {len(out)} players, {int(rank.notna().sum())} with a consensus rank, "
          f"{len(unmatched)} consensus names not in the ratings (e.g. {unmatched[:5]})")
    print(out.sort_values("blend3", ascending=False).head(10)[["name", "base", "bpv", "espn", "ecr", "blend3"]].round(0).to_string())


def score(path):
    snap = pd.read_csv(path).set_index("id")
    games = bpv.add_fpts(nba_data.player_game_logs(TARGET))
    g = games.groupby("PLAYER_ID").FPTS.agg(["sum", "mean", "size"])
    snap["act_total"] = g["sum"].reindex(snap.index).fillna(0)
    snap["act_fpg"] = np.where(g["size"].reindex(snap.index).fillna(0) >= 20, g["mean"].reindex(snap.index), np.nan)
    top = lambda c: set(snap[c].dropna().sort_values(ascending=False).head(150).index)
    pool = snap.loc[list(top("base") | top("espn") | top("ecr") | top("bpv"))]
    res = {}
    for c in ("base", "bpv", "espn", "ecr", "blend3"):
        x = pool.dropna(subset=[c])
        pg = x.dropna(subset=["act_fpg", c + "_fpg"])
        res[c] = {"n": len(x), "total_mae": float((x[c] - x.act_total).abs().mean()),
                  "rank_corr": float(x[c].rank().corr(x.act_total.rank())),
                  "fpg_mae": float((pg[c + "_fpg"] - pg.act_fpg).abs().mean()),
                  "top130_actual": float(snap.sort_values(c, ascending=False).head(130).act_total.sum())}
    b, n = res["base"], res["blend3"]
    res["decision"] = "adopt blend3" if (n["total_mae"] < b["total_mae"] and n["rank_corr"] > b["rank_corr"]) else "keep base"
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "score":
        score(sys.argv[2])
    else:
        freeze()
