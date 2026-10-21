"""Second round of single-game projection fixes (rules: docs/prereg-game-projections-fix2.md).

Chooses F1 (shape), F2 (recent minutes), F3 (teammate news from the injury report) on 2025-26 box scores, then tests
once against the 2024-25 real sportsbook lines.

    python -m analysis.game_fix2            (writes analysis/game_fix2.json)
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

import nba_data   # noqa: E402
from analysis import game_fix as gf   # noqa: E402
from analysis import real_lines as rl   # noqa: E402

gf.HALF_LIVES = (3, 5, 10, 20)
ROOT = rl.ROOT
OUT = os.path.join(ROOT, "analysis", "game_fix2.json")
STATS = ["PTS", "REB", "AST", "PRA"]
NEWS = {"Out", "Doubtful"}
RETURN_MPG = 15


def team_full_to_abbr():
    from nba_api.stats.static import teams
    return {t["full_name"]: t["abbreviation"] for t in teams.get_teams()}


def teammate_news(season):
    """(date, player id) -> V (net vacated minutes per game from new absences minus returns) and his share of the
    expected-active teammates' minutes, using only the injury report of the day and games before it."""
    games = nba_data.player_game_logs(season)
    games = games[games["MIN"] > 0]
    rep = nba_data.injury_reports(season)
    rep = rep[rep["Current Status"].isin(NEWS)].copy()
    rep["date"] = pd.to_datetime(rep["Game Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    rep = rep[rep["REPORT_DATE"] == rep["date"]]
    abbr = team_full_to_abbr()
    rep["team"] = rep["Team"].map(abbr)

    def flip(n):
        n = str(n)
        if "," in n:
            last, first = n.split(",", 1)
            n = f"{first.strip()} {last.strip()}"
        return rl.key(n)
    rep["key"] = rep["Player Name"].map(flip)
    out_by = rep.groupby(["date", "team"])["key"].apply(set).to_dict()
    games = games.assign(key=games["PLAYER_NAME"].map(rl.key))
    team_dates = games.groupby("TEAM_ABBREVIATION")["GAME_DATE"].apply(lambda s: sorted(set(s))).to_dict()
    rows = []
    for (day, team), today in games.groupby(["GAME_DATE", "TEAM_ABBREVIATION"]):
        prev_dates = [x for x in team_dates[team] if x < day][-10:]
        if not prev_dates:
            continue
        hist = games[(games["TEAM_ABBREVIATION"] == team) & games["GAME_DATE"].isin(prev_dates)]
        mpg = hist.groupby("PLAYER_ID")["MIN"].apply(lambda m: m.tail(10).mean())
        keys = hist.drop_duplicates("PLAYER_ID").set_index("PLAYER_ID")["key"]
        played_prev = set(hist[hist["GAME_DATE"] == prev_dates[-1]]["PLAYER_ID"])
        recent3 = set(hist[hist["GAME_DATE"].isin(prev_dates[-3:])]["PLAYER_ID"])
        listed = out_by.get((day, team), set())
        # Still on this team: his latest game before the day was for this team, within the last 15 days (traded,
        # waived and long-gone players aren't "returning").
        before = games[(games["GAME_DATE"] < day) & games["PLAYER_ID"].isin(mpg.index)].groupby("PLAYER_ID").tail(1).set_index("PLAYER_ID")
        cutoff = (pd.Timestamp(day) - pd.Timedelta(days=15)).strftime("%Y-%m-%d")
        on_team = {p for p in mpg.index if p in before.index and before.at[p, "TEAM_ABBREVIATION"] == team and before.at[p, "GAME_DATE"] >= cutoff}
        new_abs = [p for p in mpg.index if p in played_prev and keys[p] in listed]
        returns = [p for p in mpg.index if p not in played_prev and p in on_team and mpg[p] >= RETURN_MPG and keys[p] not in listed]
        v = float(mpg[new_abs].sum() - mpg[returns].sum()) if len(mpg) else 0.0
        active = [p for p in mpg.index if (p in recent3 or p in returns) and p in on_team | played_prev and keys[p] not in listed]
        act_sum = float(mpg[active].sum()) if active else 0.0
        for pid in today["PLAYER_ID"]:
            share = float(mpg.get(pid, 0.0)) / act_sum if act_sum > 0 else 0.0
            rows.append({"date": day, "id": pid, "V": v, "share": share, "news": bool(new_abs or returns)})
    return pd.DataFrame(rows)


def features(season, prior):
    d = gf.build(season, prior)
    n = teammate_news(season)
    d = d.merge(n, on=["date", "id"], how="left")
    d[["V", "share"]] = d[["V", "share"]].fillna(0.0)
    d["news"] = d["news"].fillna(False).astype(bool)
    return d


CURRENT = json.load(open(os.path.join(ROOT, "analysis", "game_fix.json")))["chosen"]


def means_vars(d, s, cfg):
    """game_fix.means_vars plus F2 (any half-life) and F3 (teammate news). cfg adds: shape ('nb'/'normal'), kshape,
    alpha, gamma."""
    base = {k: cfg[k] for k in ("H", "w", "opp", "c", "b2b", "home", "s", "k")}
    if s == "PRA":
        mean_p, _ = gf.means_vars(d, "PTS", base)
    mean, var = gf.means_vars(d, s, base)
    if cfg.get("alpha", 0) or cfg.get("gamma", 0):
        mh = cfg["w"] * d[f"min_ewm{cfg['H']}"] + (1 - cfg["w"]) * d["min_mean"] if cfg["H"] and cfg["w"] else d["min_mean"]
        extra = cfg.get("alpha", 0) * d["V"] * d["share"]
        minf = np.where(mh > 1, (mh + extra) / mh, 1.0)
        rate = 1.0
        if s in ("PTS", "AST"):
            rate = 1 + cfg.get("gamma", 0) * d["V"] / 240
        elif s == "PRA":
            pa = (d["PTS_mix"] + d["AST_mix"]) / np.maximum(d["PRA_mix"], 1e-6)
            rate = 1 + cfg.get("gamma", 0) * d["V"] / 240 * pa
        mean = np.maximum(0, np.asarray(mean * minf * rate, float))
    return np.asarray(mean, float), np.asarray(var, float)


def p_le(s, cfg, mean, var, x):
    """P(X <= x) under the chosen shape."""
    if cfg.get("shape") == "normal":
        return sst.norm.cdf(x, mean, np.sqrt(var * cfg.get("kshape", 1.0)))
    return gf._cdf(s, mean, var, x)


def proxy_brier(d, s, cfg):
    mean, var = means_vars(d, s, cfg)
    line = np.floor(d[f"{s}_bench"].to_numpy()) + 0.5
    pov = 1 - p_le(s, cfg, mean, var, line)
    over = (d[f"{s}_y"].to_numpy() > line).astype(float)
    return float(((pov - over) ** 2).mean())


def choose(d, s):
    cfg = {**gf.BASE, **CURRENT[s], "shape": "nb", "kshape": 1.0, "alpha": 0.0, "gamma": 0.0}
    best = proxy_brier(d, s, cfg)
    trail = [("current", round(best, 5))]

    def try_(opts, label):
        nonlocal cfg, best
        win = None
        for o in opts:
            b = proxy_brier(d, s, {**cfg, **o})
            if b < best - 1e-6:
                best, win = b, o
        if win:
            cfg = {**cfg, **win}
        trail.append((label, round(best, 5), win))
    try_([{"shape": "normal", "kshape": k} for k in (1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6)], "F1 shape")
    try_([{"H": H, "w": w} for H in (3, 5, 10, 20) for w in (0.25, 0.5, 0.75)], "F2 recent minutes")
    try_([{"alpha": a, "gamma": g} for a in (0, 0.25, 0.5, 0.75, 1.0) for g in (0, 0.5, 1, 2) if a or g], "F3 teammate news")
    return cfg, trail


def real_line_test(cfgs):
    """Brier of model-only chances at the 2024-25 consensus lines: current vs fixed, and the books' no-vig consensus."""
    lines = pd.read_csv(rl.LINES)
    lines = lines[lines["stat"].isin(["PTS", "REB", "AST"])]
    cons = rl.consensus(lines)
    feats = features(rl.SEASON, rl.PRIOR)
    names = nba_data.player_game_logs(rl.SEASON).drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    feats["key"] = feats["id"].map(names).map(rl.key)
    cons["key"] = cons["player"].map(rl.key)
    out, rows = {}, []
    for s in ("PTS", "REB", "AST"):
        cur = {**gf.BASE, **CURRENT[s], "shape": "nb"}
        fixed = cfgs[s]
        f = feats.copy()
        f["m0"], f["v0"] = means_vars(f, s, cur)
        f["m1"], f["v1"] = means_vars(f, s, fixed)
        c = cons[cons["stat"] == s].merge(f[["date", "key", "m0", "v0", "m1", "v1", "news", f"{s}_y"]], left_on=["game_date", "key"], right_on=["date", "key"])
        c = c[~np.isclose(c["line"], np.round(c["line"]))]
        over = (c[f"{s}_y"] > c["line"]).astype(float).to_numpy()
        p0 = 1 - p_le(s, cur, c["m0"].to_numpy(), c["v0"].to_numpy(), c["line"].to_numpy())
        p1 = 1 - p_le(s, fixed, c["m1"].to_numpy(), c["v1"].to_numpy(), c["line"].to_numpy())
        io, iu = 1 / c["dec_over"], 1 / c["dec_under"]
        pm = (io / (io + iu)).to_numpy()
        news = c["news"].to_numpy()
        b = lambda p, m=slice(None): float(((p[m] - over[m]) ** 2).mean())
        out[s] = {"offers": int(len(c)), "brier_current": b(p0), "brier_fixed": b(p1), "brier_market": b(pm),
                  "teammate_news_offers": int(news.sum()), "news_brier_current": b(p0, news), "news_brier_fixed": b(p1, news),
                  "news_brier_market": b(pm, news), "over_rate": float(over.mean()), "current_says": float(p0.mean()), "fixed_says": float(p1.mean())}
        rows.append((p1 - over) ** 2)
        rows.append(None)
    tot = {k: sum(out[s][k] * out[s]["offers"] for s in out) / sum(out[s]["offers"] for s in out) for k in ("brier_current", "brier_fixed", "brier_market")}
    return out, tot


def main():
    t0 = time.time()
    design = features("2025-26", "2024-25")
    print(f"design rows {len(design)}, with teammate news {int(design['news'].sum())} ({time.time() - t0:.0f}s)", flush=True)
    cfgs, trails = {}, {}
    for s in STATS:
        cfgs[s], trails[s] = choose(design, s)
        print(s, trails[s], flush=True)
    per, tot = real_line_test(cfgs)
    passes = tot["brier_fixed"] < tot["brier_current"]
    res = {"rules": "docs/prereg-game-projections-fix2.md", "chosen": cfgs, "trails": trails, "real_lines_2024_25": per,
           "total": tot, "passes": bool(passes), "seconds": round(time.time() - t0)}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=float)
    print("\nTEST vs 2024-25 real lines (Brier, lower is better):")
    for s, x in per.items():
        print(f"  {s}: current {x['brier_current']:.4f}  fixed {x['brier_fixed']:.4f}  market {x['brier_market']:.4f} | over-rate {x['over_rate']:.3f}"
              f" current says {x['current_says']:.3f} fixed says {x['fixed_says']:.3f} | teammate-news offers {x['teammate_news_offers']}:"
              f" current {x['news_brier_current']:.4f} fixed {x['news_brier_fixed']:.4f} market {x['news_brier_market']:.4f}")
    print(f"  ALL: current {tot['brier_current']:.4f}  fixed {tot['brier_fixed']:.4f}  market {tot['brier_market']:.4f}  -> passes: {passes}")


if __name__ == "__main__":
    main()
