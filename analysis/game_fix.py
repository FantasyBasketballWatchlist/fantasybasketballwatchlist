"""Fixing the single-game projections (rules: docs/prereg-game-projections-fix.md).

Builds one row per player-game (from the 15th game day on) with everything known before that day, chooses changes on
the design season (2025-26) by Brier score on the proxy lines, then runs the final version once on the test season
(2024-25).

    python -m analysis.game_fix            (writes analysis/game_fix.json)
"""
import json
import os
import time
import warnings

import numpy as np
import pandas as pd
from scipy import stats as sst

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import game_projections as gp   # noqa: E402
import nba_data   # noqa: E402

DESIGN, DESIGN_PRIOR = "2025-26", "2024-25"
TEST, TEST_PRIOR = "2024-25", "2023-24"
FIRST_DAY_INDEX, ANCHOR_K = 14, 8
HALF_LIVES = (3, 5, 10)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_fix.json")
S = gp.SHOWN


def build(season, prior):
    """One row per player-game: history features (before the day) and the outcome."""
    cur = gp.with_combos(nba_data.player_game_logs(season))
    last = gp.with_combos(nba_data.player_game_logs(prior))
    teams = nba_data.team_game_logs(season)
    curves = gp.variance_curves(last)
    last_mean = last.groupby("PLAYER_ID")[S].mean()
    last_fpts = last_mean["FPTS"]
    teams = teams.assign(OPP=teams["MATCHUP"].str[-3:], HOME=teams["MATCHUP"].str.contains("vs."))
    days = sorted(cur["GAME_DATE"].unique())
    rows = []
    for day in days[FIRST_DAY_INDEX:]:
        before = cur[cur["GAME_DATE"] < day]
        today = cur[cur["GAME_DATE"] == day]
        pids = set(today["PLAYER_ID"])
        pool = pd.concat([last[last["PLAYER_ID"].isin(pids)], before[before["PLAYER_ID"].isin(pids)]])
        pool = pool.sort_values(["GAME_DATE", "GAME_ID"])
        # Opponent allowed per stat (relative to league), from games before the day.
        tb = teams[teams["GAME_DATE"] < day]
        allowed = before.merge(tb[["GAME_ID", "TEAM_ID", "OPP"]], on=["GAME_ID", "TEAM_ID"]).groupby(["OPP", "GAME_ID"])[S].sum()
        per_opp, opp_n = allowed.groupby("OPP").mean(), allowed.groupby("OPP").size()
        rel = per_opp / per_opp.mean()
        played_yday = set(tb[tb["GAME_DATE"] == (pd.Timestamp(day) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")]["TEAM_ABBREVIATION"])
        tday = teams[teams["GAME_DATE"] == day].set_index("TEAM_ABBREVIATION")
        cur_g = before.groupby("PLAYER_ID")
        cur_n, cur_mean = cur_g.size(), cur_g[S].mean()
        for pid, hist in pool.groupby("PLAYER_ID"):
            hist = hist.tail(gp.HISTORY_GAMES)
            n = len(hist)
            if n < gp.MIN_HISTORY:
                continue
            t = today[today["PLAYER_ID"] == pid].iloc[0]
            team = t["TEAM_ABBREVIATION"]
            if team not in tday.index:
                continue
            opp = tday.at[team, "OPP"]
            nc = int(cur_n.get(pid, 0))
            bench_src = cur_mean.loc[pid] if (nc >= 3 or pid not in last_mean.index) and pid in cur_mean.index else (
                last_mean.loc[pid] if pid in last_mean.index else None)
            if bench_src is None:
                continue
            m_cur = float(cur_mean.at[pid, "FPTS"]) if nc else None
            prior_f = float(last_fpts[pid]) if pid in last_fpts.index else m_cur
            anchor = (nc * m_cur + ANCHOR_K * prior_f) / (nc + ANCHOR_K) if nc else prior_f
            mins = hist["MIN"].to_numpy(float)
            age = np.arange(n)[::-1]
            r = {"date": day, "id": pid, "n": n, "anchor": anchor, "mix_fpts": float(hist["FPTS"].mean()),
                 "min_mean": float(mins.mean()), "b2b": team in played_yday, "home": bool(tday.at[team, "HOME"]),
                 "opp_games": int(opp_n.get(opp, 0))}
            for H in HALF_LIVES:
                w = 0.5 ** (age / H)
                r[f"min_ewm{H}"] = float((w * mins).sum() / w.sum())
            for s in S:
                r[f"{s}_mix"] = float(hist[s].mean())
                r[f"{s}_var"] = float(hist[s].var()) if n > 1 else 0.0
                r[f"{s}_bench"] = float(bench_src[s])
                r[f"{s}_opp"] = float(rel.at[opp, s]) if opp in rel.index else 1.0
                r[f"{s}_y"] = float(t[s])
                a, b = curves[s]
                r[f"{s}_a"], r[f"{s}_b"] = a, b
            r["FPTS_oppf"] = r["FPTS_opp"]
            rows.append(r)
    return pd.DataFrame(rows)


# ---------- the model, vectorised, for one stat and one configuration

BASE = {"H": None, "w": 0.0, "opp": "fpts", "c": None, "b2b": 1.0, "home": 0.0, "s": 1.0, "k": 1.0}


def means_vars(d, s, cfg):
    scale = np.clip(np.where(d["mix_fpts"] > 5, d["anchor"] / d["mix_fpts"], 1.0), *gp.SCALE_RANGE)
    opp_ok = d["opp_games"] >= gp.OPP_MIN_GAMES
    if cfg["opp"] == "fpts":
        oppf = np.where(opp_ok, 1 + 0.69 * (d["FPTS_opp"] - 1), 1.0)
    else:
        oppf = np.where(opp_ok, 1 + cfg["c"] * (d[f"{s}_opp"] - 1), 1.0)
    minf = 1.0
    if cfg["H"] and cfg["w"]:
        mh = cfg["w"] * d[f"min_ewm{cfg['H']}"] + (1 - cfg["w"]) * d["min_mean"]
        minf = np.where(d["min_mean"] > 1, mh / d["min_mean"], 1.0)
    minf = minf * np.where(d["b2b"], cfg["b2b"], 1.0)
    homef = np.where(d["home"], 1 + cfg["home"], 1 - cfg["home"])
    f_old = scale * np.where(opp_ok, 1 + 0.69 * (d["FPTS_opp"] - 1), 1.0)
    f = scale * oppf * minf * homef
    mix = d[f"{s}_mix"]
    mean = mix * f if s == "FPTS" else np.maximum(0, mix * f)
    bench = d[f"{s}_bench"]
    mean = bench + cfg["s"] * (mean - bench)
    if s != "FPTS":
        mean = np.maximum(mean, 0.0)
    v_emp = d[f"{s}_var"] * f_old * f_old
    v_league = np.exp(d[f"{s}_a"] + d[f"{s}_b"] * np.log(np.maximum(mean, 0.05)))
    var = (d["n"] * v_emp + gp.VAR_K * v_league) / (d["n"] + gp.VAR_K) * cfg["k"]
    return np.asarray(mean, float), np.maximum(np.asarray(var, float), 1e-6)


def _cdf(s, mean, var, x):
    if s == "FPTS":
        return sst.norm.cdf(x, mean, np.sqrt(var))
    nb = (var > mean * 1.0001) & (mean > 1e-6)        # a zero mean is a point mass at 0, not a negative binomial
    out = sst.poisson.cdf(x, np.maximum(mean, 1e-9))
    r = np.where(nb, mean * mean / np.maximum(var - mean, 1e-9), 1.0)
    p = np.where(nb, r / (r + mean), 0.5)
    out = np.where(nb, sst.nbinom.cdf(x, r, p), out)
    return out


def metrics(d, s, cfg, rng=None):
    mean, var = means_vars(d, s, cfg)
    y, bench = d[f"{s}_y"].to_numpy(float), d[f"{s}_bench"].to_numpy(float)
    line = np.floor(bench) + 0.5
    pov = 1 - _cdf(s, mean, var, line)
    over = (y > line).astype(float)
    brier = float(((pov - over) ** 2).mean())
    p_side = np.where(pov >= 0.5, pov, 1 - pov)
    won = np.where(pov >= 0.5, y > line, y < line)
    buckets = []
    for lo, hi in zip(gp.BUCKETS[:-1], gp.BUCKETS[1:]):
        b = (p_side >= lo) & (p_side < hi)
        if b.any():
            buckets.append({"from": lo, "to": min(hi, 1.0), "n": int(b.sum()), "predicted": float(p_side[b].mean()), "actual": float(won[b].mean())})
    # Ranges: the old inclusive 10th-90th count, and randomized PIT (check 2b).
    q10 = _ppf(s, mean, var, 0.1)
    q90 = _ppf(s, mean, var, 0.9)
    inside = float(((y >= q10) & (y <= q90)).mean())
    rng = rng or np.random.default_rng(11)
    if s == "FPTS":
        u_pit = _cdf(s, mean, var, y)
    else:
        lo_c = np.where(y >= 1, _cdf(s, mean, var, y - 1), 0.0)
        u_pit = lo_c + rng.random(len(y)) * (_cdf(s, mean, var, y) - lo_c)
    pit80 = float(((u_pit > 0.1) & (u_pit < 0.9)).mean())
    return {"brier": brier, "brier_50": float(((0.5 - over) ** 2).mean()), "mae": float(np.abs(mean - y).mean()),
            "mae_bench": float(np.abs(bench - y).mean()), "inside_80": inside, "pit_80": pit80, "buckets": buckets, "n": int(len(y))}


def _ppf(s, mean, var, q):
    if s == "FPTS":
        return sst.norm.ppf(q, mean, np.sqrt(var))
    nb = (var > mean * 1.0001) & (mean > 1e-6)        # a zero mean is a point mass at 0, not a negative binomial
    r = np.where(nb, mean * mean / np.maximum(var - mean, 1e-9), 1.0)
    p = np.where(nb, r / (r + mean), 0.5)
    return np.where(nb, sst.nbinom.ppf(q, r, p), sst.poisson.ppf(q, np.maximum(mean, 1e-9)))


def loglik(d, s, cfg):
    mean, var = means_vars(d, s, cfg)
    y = d[f"{s}_y"].to_numpy(float)
    if s == "FPTS":
        return float(sst.norm.logpdf(y, mean, np.sqrt(var)).mean())
    nb = (var > mean * 1.0001) & (mean > 1e-6)        # a zero mean is a point mass at 0, not a negative binomial
    r = np.where(nb, mean * mean / np.maximum(var - mean, 1e-9), 1.0)
    p = np.where(nb, r / (r + mean), 0.5)
    return float(np.where(nb, sst.nbinom.logpmf(y, r, p), sst.poisson.logpmf(y, np.maximum(mean, 1e-9))).mean())


def choose(d, s):
    """The preregistered order: M1 grid, M2, M3, M4 (each kept only if it lowers Brier), then S, then V (likelihood)."""
    cfg, trail = dict(BASE), []
    best = metrics(d, s, cfg)["brier"]
    trail.append(("base", best))

    def try_options(options, label):
        nonlocal cfg, best
        winner = None
        for o in options:
            b = metrics(d, s, {**cfg, **o})["brier"]
            if b < best - 1e-6:
                best, winner = b, o
        if winner:
            cfg = {**cfg, **winner}
        trail.append((label, best, winner))

    try_options([{"H": H, "w": w} for H in HALF_LIVES for w in (0.5, 1.0)], "M1 recent minutes")
    try_options([{"opp": "stat", "c": c} for c in (0.0, 0.25, 0.5, 0.75, 1.0, 1.25)], "M2 opponent per stat")
    try_options([{"b2b": m} for m in (0.9, 0.93, 0.96, 0.98)], "M3 back-to-back")
    try_options([{"home": h} for h in (-0.03, -0.02, -0.01, 0.01, 0.02, 0.03)], "M4 home/away")
    try_options([{"s": x} for x in np.round(np.arange(0, 1.0, 0.1), 2)], "S shrink toward benchmark")
    ll, kbest = loglik(d, s, cfg), cfg["k"]
    for k in (0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.6):
        l2 = loglik(d, s, {**cfg, "k": k})
        if l2 > ll + 1e-6:
            ll, kbest = l2, k
    cfg["k"] = kbest
    trail.append(("V variance multiplier", metrics(d, s, cfg)["brier"], {"k": kbest}))
    return cfg, trail


def verdict(res):
    st = res
    better = {s: st[s]["mae"] < st[s]["mae_bench"] for s in ("FPTS", "PTS", "REB", "AST")}
    lines = {s: all(abs(b["predicted"] - b["actual"]) <= 0.05 for b in st[s]["buckets"] if b["n"] >= 100) and st[s]["brier"] < st[s]["brier_50"] for s in S}
    return {"accuracy": better["FPTS"] and sum(better[s] for s in ("PTS", "REB", "AST")) >= 2, "accuracy_by_stat": better,
            "ranges_old": all(0.75 <= st[s]["inside_80"] <= 0.85 for s in S),
            "ranges_2b": all(0.75 <= st[s]["pit_80"] <= 0.85 for s in S), "lines": all(lines.values()), "lines_by_stat": lines}


def main():
    t0 = time.time()
    design = build(DESIGN, DESIGN_PRIOR)
    print(f"design rows {len(design)} ({time.time() - t0:.0f}s)", flush=True)
    chosen, trails, design_res = {}, {}, {}
    for s in S:
        chosen[s], trails[s] = choose(design, s)
        design_res[s] = metrics(design, s, chosen[s])
        print(s, {k: v for k, v in chosen[s].items() if v != BASE[k]}, f"design Brier {design_res[s]['brier']:.4f} vs 0.5 {design_res[s]['brier_50']:.4f}", flush=True)
    test = build(TEST, TEST_PRIOR)
    print(f"test rows {len(test)} ({time.time() - t0:.0f}s)", flush=True)
    test_res = {s: metrics(test, s, chosen[s]) for s in S}
    test_base = {s: metrics(test, s, BASE) for s in S}
    out = {"rules": "docs/prereg-game-projections-fix.md", "chosen": chosen, "trails": {s: [list(map(lambda x: x if not isinstance(x, float) else round(x, 5), t)) for t in trails[s]] for s in S},
           "design": design_res, "test": test_res, "test_unfixed": test_base, "verdict_test": verdict(test_res),
           "verdict_test_unfixed": verdict(test_base), "rows": {"design": len(design), "test": len(test)}, "seconds": round(time.time() - t0)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=float)
    print("\nTEST 2024-25 (fixed):")
    for s in S:
        x, b0 = test_res[s], test_base[s]
        print(f"{s:5} MAE {x['mae']:.2f} (unfixed {b0['mae']:.2f}, bench {x['mae_bench']:.2f}) | 2b {x['pit_80']:.1%} | Brier {x['brier']:.4f} "
              f"(unfixed {b0['brier']:.4f}, 50% {x['brier_50']:.4f}) | " + " ".join(f"{b['from']:.2f}:{b['predicted']:.2f}/{b['actual']:.2f}({b['n']})" for b in x["buckets"]))
    print("verdict:", out["verdict_test"])


if __name__ == "__main__":
    main()
