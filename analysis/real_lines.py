"""The single-game projections against real sportsbook lines (rules: docs/prereg-real-lines.md).

    python -m analysis.real_lines            (needs data/lines/history.csv from `python -m odds_lines history ...`;
                                              writes analysis/real_lines.json, which holds results only, no raw lines)
"""
import json
import os
import re
import unicodedata
import warnings

import numpy as np
import pandas as pd
from scipy import stats as sst

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import nba_data   # noqa: E402
from analysis import game_fix as gf   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "data", "lines", "history.csv")
OUT = os.path.join(ROOT, "analysis", "real_lines.json")
SEASON, PRIOR = "2024-25", "2023-24"
STATS = ["PTS", "REB", "AST"]
THRESHOLD = 0.05
SECONDARY = [0.0, 0.10, 0.15]
BOOT = 2000


# Sportsbook spelling -> NBA spelling, for nicknames (found by checking which names didn't match, before any result).
ALIASES = {"moe wagner": "moritz wagner", "nicolas claxton": "nic claxton", "carlton carrington": "bub carrington",
           "bj boston": "brandon boston", "ron holland": "ronald holland"}


def key(name):
    n = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode().lower()
    n = re.sub(r"[.']", "", n)                      # A.J. -> aj
    n = n.replace("-", " ")
    n = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", n.strip())
    n = re.sub(r"\s+", " ", n).strip()
    return ALIASES.get(n, n)


def decimal(american):
    a = np.asarray(american, float)
    return np.where(a > 0, 1 + a / 100, 1 + 100 / np.abs(a))


def consensus(lines):
    """Per game/player/stat: the line most books offer (ties: the lower), median price per side among those books."""
    rows = []
    for (gd, ev, player, stat), g in lines.groupby(["game_date", "event_id", "player", "stat"]):
        books = g.groupby("line")["bookmaker"].nunique()
        line = books[books == books.max()].index.min()
        at = g[g["line"] == line]
        over, under = at[at["side"] == "Over"]["price"], at[at["side"] == "Under"]["price"]
        if not len(over) or not len(under):
            continue
        # Median in decimal odds: American odds jump from -100 to +100, so their own median can land on a non-price.
        rows.append({"game_date": gd, "event_id": ev, "player": player, "stat": stat, "line": float(line),
                     "dec_over": float(np.median(decimal(over))), "dec_under": float(np.median(decimal(under))),
                     "books": int(books.max())})
    return pd.DataFrame(rows)


def probabilities(stat, mean, var, line):
    """(p over, p under, p push) at the line, for the model's negative binomial / Poisson."""
    whole = np.isclose(line, np.round(line))
    le = gf._cdf(stat, mean, var, line)                                  # P(X <= line)
    below = gf._cdf(stat, mean, var, np.where(whole, line - 1, line))    # P(X < line) for whole lines
    push = np.where(whole, le - below, 0.0)
    return 1 - le, np.where(whole, below, le), push


def roi(bets, thresholds):
    out = {}
    for t in thresholds:
        b = bets[bets["ev"] > t]
        out[f"{t:.2f}"] = {"bets": int(len(b)), "roi": float(b["profit"].mean()) if len(b) else None,
                           "hit_rate": float((b["profit"] > 0).mean()) if len(b) else None,
                           "break_even": float((1 / b["dec"]).mean()) if len(b) else None}
    return out


def bootstrap(b, seed=7):
    days = b["game_date"].unique()
    by_day = {d: g["profit"].to_numpy() for d, g in b.groupby("game_date")}
    rng = np.random.default_rng(seed)
    sims = []
    for _ in range(BOOT):
        pick = rng.choice(days, len(days))
        x = np.concatenate([by_day[d] for d in pick])
        sims.append(x.mean())
    return [float(np.percentile(sims, 2.5)), float(np.percentile(sims, 97.5))]


def main():
    lines = pd.read_csv(LINES)
    lines = lines[lines["stat"].isin(STATS)]
    cons = consensus(lines)
    # Projections for every 2024-25 player-game from the 15th game day (only games before that day).
    feats = gf.build(SEASON, PRIOR)
    chosen = json.load(open(os.path.join(ROOT, "analysis", "game_fix.json")))["chosen"]
    names = nba_data.player_game_logs(SEASON).drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    feats["key"] = feats["id"].map(names).map(key)
    cons["key"] = cons["player"].map(key)
    bets, matched_rows = [], 0
    unmatched = set()
    calib = []
    for stat in STATS:
        mean, var = gf.means_vars(feats, stat, chosen[stat])
        f = feats.assign(mean=mean, var=var)[["date", "key", "mean", "var", f"{stat}_y"]].rename(columns={f"{stat}_y": "y"})
        c = cons[cons["stat"] == stat].merge(f, left_on=["game_date", "key"], right_on=["date", "key"], how="left")
        unmatched |= set(c[c["mean"].isna()]["player"])
        c = c.dropna(subset=["mean"])
        matched_rows += len(c)
        po, pu, pp = probabilities(stat, c["mean"].to_numpy(), c["var"].to_numpy(), c["line"].to_numpy())
        d_o, d_u = c["dec_over"].to_numpy(), c["dec_under"].to_numpy()
        ev_o, ev_u = po * (d_o - 1) - pu, pu * (d_u - 1) - po
        take_over = ev_o >= ev_u
        y, line = c["y"].to_numpy(), c["line"].to_numpy()
        win = np.where(take_over, y > line, y < line)
        push = y == line
        dec = np.where(take_over, d_o, d_u)
        profit = np.where(push, 0.0, np.where(win, dec - 1, -1.0))
        bets.append(pd.DataFrame({"game_date": c["game_date"], "stat": stat, "player": c["player"], "line": line,
                                  "side": np.where(take_over, "over", "under"), "p_side": np.where(take_over, po, pu),
                                  "ev": np.maximum(ev_o, ev_u), "dec": dec, "profit": profit}))
        # Calibration and the market comparison, on every offer (half-point lines, no pushes).
        half = ~np.isclose(line, np.round(line))
        imp_o, imp_u = 1 / d_o, 1 / d_u
        market_over = imp_o / (imp_o + imp_u)
        calib.append(pd.DataFrame({"stat": stat, "p_over": po[half], "market_over": market_over[half], "over": (y[half] > line[half]).astype(float)}))
    bets = pd.concat(bets, ignore_index=True)
    cal = pd.concat(calib, ignore_index=True)

    primary = bets[bets["ev"] > THRESHOLD]
    mid = np.median(pd.to_datetime(primary["game_date"]).astype("int64"))
    first = primary[pd.to_datetime(primary["game_date"]).astype("int64") <= mid]
    second = primary[pd.to_datetime(primary["game_date"]).astype("int64") > mid]
    res = {"rules": "docs/prereg-real-lines.md", "games": int(cons["event_id"].nunique()), "offers": int(len(cons)),
           "offers_matched": int(matched_rows), "players_unmatched": len(unmatched),
           "dates": [str(cons["game_date"].min()), str(cons["game_date"].max())],
           "primary": {"threshold": THRESHOLD, "bets": int(len(primary)), "roi": float(primary["profit"].mean()),
                       "ci95": bootstrap(primary), "hit_rate": float((primary["profit"] > 0).mean()),
                       "break_even": float((1 / primary["dec"]).mean()),
                       "first_half_roi": float(first["profit"].mean()), "second_half_roi": float(second["profit"].mean())},
           "thresholds": roi(bets, SECONDARY + [THRESHOLD]),
           "by_stat": {s: roi(bets[bets["stat"] == s], [THRESHOLD]) for s in STATS},
           "brier": {"model": float(((cal["p_over"] - cal["over"]) ** 2).mean()),
                     "market_no_vig": float(((cal["market_over"] - cal["over"]) ** 2).mean()), "offers": int(len(cal))}}
    p_side = np.where(cal["p_over"] >= 0.5, cal["p_over"], 1 - cal["p_over"])
    won = np.where(cal["p_over"] >= 0.5, cal["over"] == 1, cal["over"] == 0)
    res["calibration"] = [{"from": lo, "n": int(m.sum()), "predicted": float(p_side[m].mean()), "actual": float(won[m].mean())}
                          for lo, hi in zip([0.5, 0.55, 0.6, 0.65, 0.7, 0.75], [0.55, 0.6, 0.65, 0.7, 0.75, 1.01])
                          for m in [(p_side >= lo) & (p_side < hi)] if m.any()]
    pr = res["primary"]
    res["passes"] = bool(pr["roi"] > 0 and pr["ci95"][0] > 0 and pr["first_half_roi"] > 0 and pr["second_half_roi"] > 0)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
