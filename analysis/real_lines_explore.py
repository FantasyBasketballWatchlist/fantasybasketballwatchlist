"""Where do the single-game projections go wrong against real lines? (exploration; not a test)

Design: 2024-11-06 to 2024-12-31. Check: 2025-01-01 to 2025-01-29 (its overall result was already seen in
analysis/real_lines.py, so it's a weak check). Anything that survives still needs fresh lines the model has never seen.

    python -m analysis.real_lines_explore            (writes analysis/real_lines_explore.json)
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import nba_data   # noqa: E402
from analysis import game_fix as gf   # noqa: E402
from analysis import real_lines as rl   # noqa: E402

OUT = os.path.join(rl.ROOT, "analysis", "real_lines_explore.json")
SPLIT = "2025-01-01"


def offers():
    """Every matched offer: model and market chances, prices, outcome, and features to slice by."""
    lines = pd.read_csv(rl.LINES)
    lines = lines[lines["stat"].isin(rl.STATS)]
    cons = rl.consensus(lines)
    feats = gf.build(rl.SEASON, rl.PRIOR)
    chosen = json.load(open(os.path.join(rl.ROOT, "analysis", "game_fix.json")))["chosen"]
    names = nba_data.player_game_logs(rl.SEASON).drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    feats["key"] = feats["id"].map(names).map(rl.key)
    cons["key"] = cons["player"].map(rl.key)
    out = []
    for stat in rl.STATS:
        mean, var = gf.means_vars(feats, stat, chosen[stat])
        f = feats.assign(mean=mean, var=var)[["date", "key", "mean", "var", f"{stat}_y", f"{stat}_bench", "min_mean", "min_ewm3", "b2b", "home", "n"]]
        f = f.rename(columns={f"{stat}_y": "y", f"{stat}_bench": "bench"})
        c = cons[cons["stat"] == stat].merge(f, left_on=["game_date", "key"], right_on=["date", "key"]).copy()
        line = c["line"].to_numpy()
        half = ~np.isclose(line, np.round(line))
        c = c[half].copy()
        po, pu, _ = rl.probabilities(stat, c["mean"].to_numpy(), c["var"].to_numpy(), c["line"].to_numpy())
        imp_o, imp_u = 1 / c["dec_over"], 1 / c["dec_under"]
        c["p_model"] = po
        c["p_market"] = imp_o / (imp_o + imp_u)               # no-vig chance of the over
        c["over"] = (c["y"] > c["line"]).astype(float)
        out.append(c)
    return pd.concat(out, ignore_index=True)


logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
expit = lambda x: 1 / (1 + np.exp(-x))


def bets(d, p, threshold=0.05):
    """Bet the side with the higher expected profit at the median prices if above threshold. Returns per-bet profit."""
    ev_o = p * (d["dec_over"] - 1) - (1 - p)
    ev_u = (1 - p) * (d["dec_under"] - 1) - p
    over = ev_o >= ev_u
    ev = np.where(over, ev_o, ev_u)
    win = np.where(over, d["over"] == 1, d["over"] == 0)
    dec = np.where(over, d["dec_over"], d["dec_under"])
    profit = np.where(win, dec - 1, -1.0)
    m = ev > threshold
    return pd.DataFrame({"profit": profit[m], "over": over[m], "stat": d["stat"].to_numpy()[m], "game_date": d["game_date"].to_numpy()[m]})


def summary(b):
    return {"bets": int(len(b)), "roi": float(b["profit"].mean()) if len(b) else None,
            "hit": float((b["profit"] > 0).mean()) if len(b) else None}


def brier(p, y):
    return float(((p - y) ** 2).mean())


def main():
    d = offers()
    des, chk = d[d["game_date"] < SPLIT].copy(), d[d["game_date"] >= SPLIT].copy()
    res = {"offers": {"design": len(des), "check": len(chk)}}

    # 1. Where is the model wrong? Slices on the design period: model minus market, and who was closer.
    des["gap"] = des["p_model"] - des["p_market"]
    slices = {}
    def slice_(name, mask):
        x = des[mask]
        if len(x) < 200:
            return
        slices[name] = {"n": int(len(x)), "brier_model": brier(x["p_model"], x["over"]), "brier_market": brier(x["p_market"], x["over"]),
                        "over_rate": float(x["over"].mean()), "model_over": float(x["p_model"].mean()), "market_over": float(x["p_market"].mean())}
    for s in rl.STATS:
        slice_(f"stat={s}", des["stat"] == s)
    slice_("model says over", des["gap"] > 0)
    slice_("model says under", des["gap"] < 0)
    for lo, hi in [(0, .05), (.05, .1), (.1, .2), (.2, 1)]:
        slice_(f"|model-market| {lo}-{hi}", (des["gap"].abs() >= lo) & (des["gap"].abs() < hi))
    slice_("recent minutes up 3+", des["min_ewm3"] - des["min_mean"] >= 3)
    slice_("recent minutes down 3+", des["min_ewm3"] - des["min_mean"] <= -3)
    slice_("back-to-back", des["b2b"])
    slice_("line above season avg", des["line"] > des["bench"])
    slice_("line below season avg", des["line"] < des["bench"])
    res["slices_design"] = slices

    # 2. Fixes fitted on the design period, then applied unchanged to the check period.
    fits = {}
    # 2a. Shrink the model toward 50/50: p = expit(a * logit(model)).
    grid = np.round(np.arange(0.0, 1.01, 0.05), 2)
    a_best = min(grid, key=lambda a: brier(expit(a * logit(des["p_model"])), des["over"]))
    fits["model shrunk to 50/50"] = ("a", float(a_best), lambda x: expit(a_best * logit(x["p_model"])))
    # 2b. Blend with the market: p = expit(logit(market) + b * (logit(model) - logit(market))), b per stat.
    b_best = {}
    for s in rl.STATS:
        x = des[des["stat"] == s]
        b_best[s] = float(min(grid, key=lambda b: brier(expit(logit(x["p_market"]) + b * (logit(x["p_model"]) - logit(x["p_market"]))), x["over"])))
    fits["blend with market"] = ("b", b_best, lambda x: expit(logit(x["p_market"]) + x["stat"].map(b_best).to_numpy() * (logit(x["p_model"]) - logit(x["p_market"]))))
    fits["market alone"] = ("-", None, lambda x: x["p_market"])
    fits["model alone"] = ("-", None, lambda x: x["p_model"])

    table = {}
    for name, (pname, param, fn) in fits.items():
        row = {"param": param}
        for label, x in (("design", des), ("check", chk)):
            p = np.asarray(fn(x), float)
            row[f"{label}_brier"] = brier(p, x["over"])
            for t in (0.0, 0.03, 0.05, 0.10):
                row[f"{label}_ev>{t:.2f}"] = summary(bets(x, p, t))
        table[name] = row
    res["fixes"] = table
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1, default=float)

    print(f"offers: design {len(des)}, check {len(chk)}\n\nWHERE IT GOES WRONG (design, Brier: lower is better)")
    for k, v in slices.items():
        print(f"  {k:28} n={v['n']:5}  model {v['brier_model']:.4f}  market {v['brier_market']:.4f}  over-rate {v['over_rate']:.3f}  model says {v['model_over']:.3f}  market says {v['market_over']:.3f}")
    print("\nFIXES (fitted on design, applied unchanged to check)")
    for name, r in table.items():
        print(f"  {name:22} param={r['param']}  Brier design {r['design_brier']:.4f} check {r['check_brier']:.4f}")
        for t in ("0.00", "0.03", "0.05", "0.10"):
            a, b = r[f"design_ev>{t}"], r[f"check_ev>{t}"]
            f = lambda s: f"{s['bets']:5} bets ROI {s['roi']:+.3f}" if s["bets"] else "    0 bets"
            print(f"      EV>{t}: design {f(a)} | check {f(b)}")


if __name__ == "__main__":
    main()
