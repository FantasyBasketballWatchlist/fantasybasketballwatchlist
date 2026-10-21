"""Search for profitable corners of the player-prop market, then confirm them on separate data
(rules: docs/prereg-corners.md).

    python -m analysis.corners history      2024-25 single snapshot, profit; discover Nov-Dec, confirm January
    python -m analysis.corners live         forward snapshots (data/lines/live), closing-line value; discover on the
                                            first half of game days, confirm on the second
    python -m analysis.corners morning      past morning prices (data/lines/history_morning.csv) vs the near-close
                                            prices (data/lines/history.csv), closing-line value; discover on one season,
                                            confirm on another

Writes data/tracking/corners_<source>.json (results only: corner names and statistics, no raw lines).
"""
import argparse
import datetime
import glob
import itertools
import json
import os
import warnings

import numpy as np
import pandas as pd
from scipy import stats as sst

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "data", "lines")
TRACK = os.path.join(ROOT, "data", "tracking")
LICENSED = {"draftkings", "fanduel", "betmgm", "williamhill_us", "betrivers", "espnbet", "fanatics", "ballybet",
            "hardrockbet", "betparx"}
STATS = ["PTS", "REB", "AST"]
MIN_BETS = 300
FDR_Q = 0.10
CONFIRM_P = 0.05
TAGS = ["time", "book", "stat", "side", "price", "value", "size", "model"]


def decimal(a):
    a = np.asarray(a, float)
    return np.where(a > 0, 1 + a / 100, 1 + 100 / np.abs(a))


def wide(prices):
    """One row per game/player/stat/line/book with both sides' decimal odds and that book's no-vig over chance."""
    p = prices[prices["stat"].isin(STATS)].copy()
    p["dec"] = decimal(p["price"])
    w = p.pivot_table(index=["game_date", "event_id", "player", "stat", "line", "bookmaker"], columns="side",
                      values="dec", aggfunc="first").dropna().reset_index()
    w = w[~np.isclose(w["line"], np.round(w["line"]))]
    io, iu = 1 / w["Over"], 1 / w["Under"]
    w["nv_over"] = io / (io + iu)
    return w


def bets_from(w):
    """Both sides of every licensed price, tagged (book, stat, side, price, value vs the other books)."""
    key = ["event_id", "player", "stat", "line"]
    g = w.groupby(key)
    w = w.assign(n=g["bookmaker"].transform("count"), s=g["nv_over"].transform("sum"))
    w["fair_loo"] = np.where(w["n"] >= 4, (w["s"] - w["nv_over"]) / (w["n"] - 1).clip(lower=1), np.nan)
    w = w[w["bookmaker"].isin(LICENSED)]
    o = w.assign(side="over", dec=w["Over"], p_fair_loo=w["fair_loo"])
    u = w.assign(side="under", dec=w["Under"], p_fair_loo=1 - w["fair_loo"])
    b = pd.concat([o, u], ignore_index=True)
    b["ev_loo"] = b["p_fair_loo"] * b["dec"] - 1
    b["book"] = b["bookmaker"]
    b["price"] = np.where(b["dec"] < 1.87, "favourite", np.where(b["dec"] <= 2.0, "middle", "underdog"))
    b["value"] = pd.cut(b["ev_loo"], [-np.inf, 0, 0.02, 0.04, np.inf], labels=["<0", "0-2%", "2-4%", "4%+"]).astype(str)
    b.loc[b["ev_loo"].isna(), "value"] = "n/a"
    return b[["game_date", "event_id", "player", "stat", "line", "book", "side", "dec", "price", "value"]]


def add_size(b, cuts):
    b = b.copy()
    b["size"] = "middle"
    for s in STATS:
        lo, hi = cuts[s]
        m = b["stat"] == s
        b.loc[m & (b["line"] < lo), "size"] = "low"
        b.loc[m & (b["line"] > hi), "size"] = "high"
    return b


def size_cuts(b):
    return {s: tuple(np.quantile(b.loc[b["stat"] == s, "line"], [1 / 3, 2 / 3])) for s in STATS if (b["stat"] == s).any()}


def corners(b, metric):
    """Every single tag and pair of tags with MIN_BETS+ bets: mean metric, game-clustered SE, one-sided p."""
    out = []
    for k in (1, 2):
        for cols in itertools.combinations(TAGS, k):
            for vals, grp in b.groupby(list(cols)):
                vals = vals if isinstance(vals, tuple) else (vals,)
                if len(grp) < MIN_BETS or "n/a" in vals:
                    continue
                per_game = grp.groupby("event_id")[metric].agg(["sum", "size"])
                mean = per_game["sum"].sum() / per_game["size"].sum()
                # Cluster-robust SE of a ratio mean (by game).
                resid = per_game["sum"] - mean * per_game["size"]
                g = len(per_game)
                se = float(np.sqrt((resid ** 2).sum() * g / max(g - 1, 1)) / per_game["size"].sum())
                z = mean / se if se > 0 else 0.0
                out.append({"corner": " + ".join(f"{c}={v}" for c, v in zip(cols, vals)), "tags": dict(zip(cols, vals)),
                            "bets": int(len(grp)), "games": int(g), "mean": float(mean), "se": se, "p": float(1 - sst.norm.cdf(z))})
    return out


def bh(found, q=FDR_Q):
    """Benjamini-Hochberg: the corners kept at false discovery rate q."""
    found = sorted(found, key=lambda x: x["p"])
    m = len(found)
    keep = 0
    for i, c in enumerate(found, 1):
        if c["p"] <= q * i / m:
            keep = i
    return found[:keep]


def measure_in(b, tags, metric):
    m = np.ones(len(b), bool)
    for c, v in tags.items():
        m &= (b[c].astype(str) == str(v)).to_numpy()
    grp = b[m]
    if not len(grp):
        return {"bets": 0}
    per_game = grp.groupby("event_id")[metric].agg(["sum", "size"])
    mean = per_game["sum"].sum() / per_game["size"].sum()
    resid = per_game["sum"] - mean * per_game["size"]
    g = len(per_game)
    se = float(np.sqrt((resid ** 2).sum() * g / max(g - 1, 1)) / per_game["size"].sum()) if g > 1 else float("nan")
    p = float(1 - sst.norm.cdf(mean / se)) if se and se > 0 else 1.0
    return {"bets": int(len(grp)), "games": int(g), "mean": float(mean), "se": se, "p": p}


def run(discover, confirm, metric, label, extra=None):
    cuts = size_cuts(discover)
    discover, confirm = add_size(discover, cuts), add_size(confirm, cuts)
    tested = corners(discover, metric)
    kept = bh(tested)
    results = []
    for c in kept:
        conf = measure_in(confirm, c["tags"], metric)
        results.append({**c, "confirm": conf, "confirmed": bool(conf.get("bets", 0) and conf["mean"] > 0 and conf["p"] < CONFIRM_P)})
    best = sorted(tested, key=lambda x: x["p"])[:10]
    res = {"rules": "docs/prereg-corners.md", "source": label, "metric": metric, "updated": datetime.date.today().isoformat(),
           "discover_bets": int(len(discover)), "confirm_bets": int(len(confirm)), "corners_tested": len(tested),
           "discovered": len(kept), "confirmed": [r for r in results if r["confirmed"]], "all_discovered": results,
           "baseline": {"discover": float(discover[metric].mean()), "confirm": float(confirm[metric].mean()) if len(confirm) else None},
           "top10_before_correction": [{k: v for k, v in c.items() if k != "tags"} for c in best], **(extra or {})}
    os.makedirs(TRACK, exist_ok=True)
    with open(os.path.join(TRACK, f"corners_{label}.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=float)
    print(f"{label}: {res['discover_bets']} discovery bets, {res['confirm_bets']} confirmation bets, {len(tested)} corners tested; "
          f"baseline {metric} {res['baseline']['discover']:+.4f} / {res['baseline']['confirm'] if res['baseline']['confirm'] is None else round(res['baseline']['confirm'], 4)}")
    print(f"  discovered (FDR {FDR_Q:.0%}): {len(kept)}; confirmed: {len(res['confirmed'])}")
    for r in results:
        c = r["confirm"]
        print(f"   {r['corner']:55} disc {r['mean']:+.4f} (n={r['bets']}, p={r['p']:.4f}) | confirm "
              + (f"{c['mean']:+.4f} (n={c['bets']}, p={c['p']:.3f})" if c.get("bets") else "no bets") + ("  CONFIRMED" if r["confirmed"] else ""))
    print("  strongest before correction:")
    for c in best[:5]:
        print(f"   {c['corner']:55} {c['mean']:+.4f} (n={c['bets']}, p={c['p']:.4f})")
    return res


# ---------- model tag

def model_over_history(season, prior):
    """(game_date, player key, stat) -> P(over) at a line is needed per line; returns a function of (rows)."""
    import nba_data
    from analysis import game_fix2 as g2
    from analysis.real_lines import key
    feats = g2.features(season, prior)
    names = nba_data.player_game_logs(season).drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    feats["key"] = feats["id"].map(names).map(key)
    cfgs = json.load(open(os.path.join(ROOT, "analysis", "game_fix2.json")))["chosen"]
    tabs = {}
    for s in STATS:
        m, v = g2.means_vars(feats, s, cfgs[s])
        tabs[s] = (feats.assign(m=m, v=v)[["date", "key", "m", "v", f"{s}_y"]], cfgs[s])
    return tabs


def tag_model_and_outcome(b, tabs):
    from analysis import game_fix2 as g2
    from analysis.real_lines import key
    out = []
    b = b.assign(key=b["player"].map(key))
    for s in STATS:
        t, cfg = tabs[s]
        x = b[b["stat"] == s].merge(t.rename(columns={f"{s}_y": "y"}), left_on=["game_date", "key"], right_on=["date", "key"])
        p_over = 1 - g2.p_le(s, cfg, x["m"].to_numpy(), x["v"].to_numpy(), x["line"].to_numpy())
        x["model"] = np.where((p_over > 0.5) == (x["side"] == "over"), "favours", "against")
        out.append(x)
    x = pd.concat(out, ignore_index=True)
    won = np.where(x["side"] == "over", x["y"] > x["line"], x["y"] < x["line"])
    x["profit"] = np.where(won, x["dec"] - 1, -1.0)
    return x


def history():
    prices = pd.read_csv(os.path.join(LINES, "history.csv"))
    b = bets_from(wide(prices)).assign(time="pre-tip")
    tabs = model_over_history("2024-25", "2023-24")
    b = tag_model_and_outcome(b, tabs)
    d, c = b[b["game_date"] < "2025-01-01"], b[b["game_date"] >= "2025-01-01"]
    return run(d, c, "profit", "history")


def clv_bets(morning_prices, close_prices):
    """Morning bets with closing-line value against the consensus no-vig close (same line)."""
    b = bets_from(wide(morning_prices))
    cw = wide(close_prices)
    fair = cw.groupby(["event_id", "player", "stat", "line"])["nv_over"].mean().rename("fair_close").reset_index()
    b = b.merge(fair, on=["event_id", "player", "stat", "line"])
    p_side = np.where(b["side"] == "over", b["fair_close"], 1 - b["fair_close"])
    b["clv"] = b["dec"] * p_side - 1
    return b


def model_tag_live(b):
    pred_path = os.path.join(TRACK, "game_predictions.csv")
    if not os.path.exists(pred_path):
        return b.assign(model="n/a")
    import game_projections as gp
    from analysis.real_lines import key
    pred = pd.read_csv(pred_path)
    pred["key"] = pred["name"].map(key)
    b = b.assign(key=b["player"].map(key), model="n/a")
    for s in STATS:
        m = b["stat"] == s
        x = b[m].merge(pred[["date", "key", f"{s}_mean", f"{s}_var"]], left_on=["game_date", "key"], right_on=["date", "key"], how="left")
        p = np.array([1 - gp.cdf(gp.dist_of(s), mu, va, ln) if pd.notna(mu) else np.nan
                      for mu, va, ln in zip(x[f"{s}_mean"], x[f"{s}_var"], x["line"])])
        tag = np.where(np.isnan(p), "n/a", np.where((p > 0.5) == (x["side"] == "over").to_numpy(), "favours", "against"))
        b.loc[m, "model"] = tag
    return b


def live():
    files = sorted(glob.glob(os.path.join(LINES, "live", "*.csv")))
    if not files:
        print("No live snapshots yet.")
        return None
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    both = set(d.loc[d["kind"] == "morning", "event_id"]) & set(d.loc[d["kind"] == "close", "event_id"])
    d = d[d["event_id"].isin(both)]
    early = []
    for kind in ("morning", "afternoon"):                          # bets placed at each early snapshot, judged at the close
        if (d["kind"] == kind).any():
            early.append(clv_bets(d[d["kind"] == kind], d[d["kind"] == "close"]).assign(time=kind))
    b = model_tag_live(pd.concat(early, ignore_index=True)) if early else pd.DataFrame(columns=["game_date", "clv"])
    days = sorted(b["game_date"].unique())
    if len(days) < 4:
        print(f"Only {len(days)} game day(s) with morning and closing prices; the search needs more.")
        res = {"rules": "docs/prereg-corners.md", "source": "live", "updated": datetime.date.today().isoformat(), "game_days": len(days),
               "bets": int(len(b)), "mean_clv": float(b["clv"].mean()) if len(b) else None, "status": "collecting"}
        os.makedirs(TRACK, exist_ok=True)
        with open(os.path.join(TRACK, "corners_live.json"), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1)
        return res
    half = days[len(days) // 2]
    return run(b[b["game_date"] < half], b[b["game_date"] >= half], "clv", "live", {"game_days": len(days)})


def morning():
    m = pd.read_csv(os.path.join(LINES, "history_morning.csv"))
    c = pd.read_csv(os.path.join(LINES, "history.csv"))
    b = clv_bets(m, c).assign(model="n/a", time="morning")
    seasons = b["game_date"].map(lambda d: d[:4] if d[5:7] >= "07" else str(int(d[:4]) - 1))
    first = sorted(seasons.unique())
    if len(first) < 2:
        days = sorted(b["game_date"].unique())
        half = days[len(days) // 2]
        return run(b[b["game_date"] < half], b[b["game_date"] >= half], "clv", "morning")
    return run(b[seasons == first[0]], b[seasons != first[0]], "clv", "morning")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", choices=["history", "live", "morning"])
    a = ap.parse_args()
    {"history": history, "live": live, "morning": morning}[a.source]()
