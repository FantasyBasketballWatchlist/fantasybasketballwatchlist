"""Closing-line value (CLV) of morning bets, from the forward snapshots (odds_lines.py auto -> data/lines/live/).

CLV = the price you got / the fair closing price - 1, where the fair closing price is the consensus of every book's
no-vig chance at the close (same line). Positive average CLV is the standard sign of an edge, and it needs far fewer
bets than profit to show one. Bets are judged at the morning snapshot, at US-licensed books only.

Strategies scored (each against the same close):
- all:      every licensed morning price (placebo: should come out near minus the books' margin)
- value:    licensed morning prices beating the other books' morning no-vig consensus by 2%+ (value / EV betting)
- model:    the morning side the single-game projection favours (data/tracking/game_predictions.csv), blended with the
            morning market as in docs/prereg-real-lines-rules.md, at the best licensed price, 3%+ expected value

    python -m analysis.clv            (writes analysis/clv.json; results only)
"""
import glob
import json
import os
import warnings

import numpy as np
import pandas as pd
from scipy import stats as sst

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, "data", "lines", "live")
PRED = os.path.join(ROOT, "data", "tracking", "game_predictions.csv")
OUT = os.path.join(ROOT, "analysis", "clv.json")
LICENSED = {"draftkings", "fanduel", "betmgm", "williamhill_us", "betrivers", "espnbet", "fanatics", "ballybet",
            "hardrockbet", "betparx"}
VALUE_EDGE, MODEL_EV = 0.02, 0.03
VAR_MULT = 1.4
BLEND_W = {"PTS": 0.10, "REB": 0.20, "AST": 0.30}
logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
expit = lambda x: 1 / (1 + np.exp(-x))


def decimal(a):
    a = np.asarray(a, float)
    return np.where(a > 0, 1 + a / 100, 1 + 100 / np.abs(a))


def load():
    files = sorted(glob.glob(os.path.join(LIVE, "*.csv")))
    if not files:
        return None
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d["dec"] = decimal(d["price"])
    w = d.pivot_table(index=["kind", "game_date", "event_id", "player", "stat", "line", "bookmaker"], columns="side",
                      values="dec", aggfunc="first").dropna().reset_index()
    io, iu = 1 / w["Over"], 1 / w["Under"]
    w["nv_over"] = io / (io + iu)
    return w


def clv_rows(bets, close_fair):
    """bets: event_id, player, stat, line, side, dec. close_fair: consensus no-vig chance of the over at the close."""
    m = bets.merge(close_fair, on=["event_id", "player", "stat", "line"], how="left")
    p_side = np.where(m["side"] == "over", m["fair_close"], 1 - m["fair_close"])
    m["clv"] = m["dec"] * p_side - 1                     # = price / fair price - 1
    return m


def summarize(m):
    m = m.dropna(subset=["clv"])
    if not len(m):
        return {"bets": 0}
    by_game = m.groupby("event_id")["clv"].mean()
    se = float(by_game.std(ddof=1) / np.sqrt(len(by_game))) if len(by_game) > 1 else None
    return {"bets": int(len(m)), "games": int(len(by_game)), "mean_clv": float(m["clv"].mean()),
            "se_by_game": se, "beat_close": float((m["clv"] > 0).mean())}


def main():
    w = load()
    if w is None:
        print("No forward snapshots yet (data/lines/live/).")
        return
    morning, close = w[w["kind"] == "morning"].copy(), w[w["kind"] == "close"].copy()
    key = ["event_id", "player", "stat", "line"]
    close_fair = close.groupby(key)["nv_over"].mean().rename("fair_close").reset_index()
    res = {"days": sorted(w["game_date"].unique().tolist()), "morning_prices": int(len(morning)), "close_prices": int(len(close))}
    lic = morning[morning["bookmaker"].isin(LICENSED)]

    # all (placebo): both sides of every licensed morning price
    allb = pd.concat([lic.assign(side="over", dec=lic["Over"]), lic.assign(side="under", dec=lic["Under"])])[key + ["side", "dec", "bookmaker"]]
    res["all"] = summarize(clv_rows(allb, close_fair))

    # value: vs the other books' morning consensus (leave-one-out), 4+ books on the line
    g = morning.groupby(key)
    morning["n"] = g["bookmaker"].transform("count")
    morning["fair_m"] = (g["nv_over"].transform("sum") - morning["nv_over"]) / (morning["n"] - 1)
    v = morning[(morning["n"] >= 4) & morning["bookmaker"].isin(LICENSED)]
    vo = v[v["fair_m"] * v["Over"] - 1 > VALUE_EDGE].assign(side="over", dec=lambda x: x["Over"])
    vu = v[(1 - v["fair_m"]) * v["Under"] - 1 > VALUE_EDGE].assign(side="under", dec=lambda x: x["Under"])
    res["value"] = summarize(clv_rows(pd.concat([vo, vu])[key + ["side", "dec", "bookmaker"]], close_fair))

    # model picks
    if os.path.exists(PRED):
        import game_projections as gp
        from analysis.real_lines import key as name_key
        pred = pd.read_csv(PRED)
        pred["k"] = pred["name"].map(name_key)
        cons = morning.groupby(key + ["game_date"]).agg(p_market=("nv_over", "mean")).reset_index()
        best = lic.groupby(key).agg(best_over=("Over", "max"), best_under=("Under", "max")).reset_index()
        cons = cons.merge(best, on=key)
        cons["k"] = cons["player"].map(name_key)
        rows = []
        for st in ("PTS", "REB", "AST"):
            c = cons[cons["stat"] == st].merge(pred[["date", "k", f"{st}_mean", f"{st}_var"]], left_on=["game_date", "k"], right_on=["date", "k"])
            if not len(c):
                continue
            pm = 1 - sst.norm.cdf(c["line"], c[f"{st}_mean"], np.sqrt(c[f"{st}_var"] * VAR_MULT))
            p = expit(logit(c["p_market"]) + BLEND_W[st] * (logit(pm) - logit(c["p_market"])))
            ev_o, ev_u = p * c["best_over"] - 1, (1 - p) * c["best_under"] - 1
            over = ev_o >= ev_u
            c = c.assign(side=np.where(over, "over", "under"), dec=np.where(over, c["best_over"], c["best_under"]), ev=np.maximum(ev_o, ev_u))
            rows.append(c[c["ev"] >= MODEL_EV])
        res["model"] = summarize(clv_rows(pd.concat(rows)[key + ["side", "dec"]], close_fair)) if rows else {"bets": 0}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
