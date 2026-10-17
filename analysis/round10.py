"""Round 10, items 1-4 (docs/prereg-round10.md): ECR blend, gap decomposition, ESPN minutes, slice weights.

Run:  python -m analysis.round10        (writes analysis/round10.json)
"""
import json
import math
import os
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_espn_projections as te_
from analysis import test_minutes_model as tmm
from analysis import test_public_rankings as pr
from analysis import test_ten_team as tt
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "round10.json")
SEASONS = list(te_.ESPN_SEASONS)
RNG = np.random.default_rng(10)
B = 2000


# ---------------------------------------------------------------- data
def espn_full(year, names):
    rows = []
    for p in te_.fetch(year)["players"]:
        pl = p["player"]
        for s in pl.get("stats", []):
            if s["statSourceId"] == 1 and s["statSplitTypeId"] == 0 and s["seasonId"] == year:
                avg, gp = s.get("averageStats") or {}, s["stats"].get(te_.GP_ID, 0.0)
                if not avg or not gp:
                    continue
                rows.append({"PLAYER_ID": names.get(te_.key(pl["fullName"])), "espn_fpg": te_.fpts(avg),
                             "espn_gp": gp, "espn_min": avg.get("40", np.nan)})
    return pd.DataFrame(rows).dropna(subset=["PLAYER_ID"]).drop_duplicates("PLAYER_ID").set_index("PLAYER_ID")


def ecr_ranks(season, names):
    ids, _ = pr.to_ids(pr.public_lists(season)["fp_ecr"], names)
    return pd.Series(np.arange(1, len(ids) + 1), index=ids)


def season_data(pg, tg, hist, league_p, league_q, t, names, debuts):
    """One row per player known before season t or who played in it, with every source's projection."""
    prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
    df, R = bt.preseason_frame(pg, hist, t, ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K, league_p, league_q,
                               age_curve=bt.age_curve_before(pg, t))
    age_prod = (df["BPV + age"] - (1 - df.p_hat) * league_q * R) / df.p_hat
    ctx = tmm.roster_context(pg, t)
    h_prev = hist[hist.season == prev].set_index("PLAYER_ID")
    prev_mpg = h_prev.mpg.reindex(df.index)
    crowd = ctx.crowding.reindex(df.index).fillna(0)
    df["bpv_fpg"] = age_prod + ratings.CROWDING_COEF * crowd.where(prev_mpg >= ratings.CROWDING_MIN_PREV_MPG, 0)
    df["prev_mpg"] = prev_mpg
    team_games = int(tg[t].groupby("TEAM_ID").size().median())

    h_t = hist[hist.season == t].set_index("PLAYER_ID")
    espn = espn_full(te_.ESPN_SEASONS[t], names)
    ecr = ecr_ranks(t, names)
    ids = df.index.union(h_t.index).union(espn.index).union(ecr.index)
    d = pd.DataFrame(index=ids)
    d["season"] = t
    for c in ("bpv_fpg", "p_hat", "prev_mpg"):
        d[c] = df[c].reindex(ids)
    for c in ("espn_fpg", "espn_gp", "espn_min"):
        d[c] = espn[c].reindex(ids)
    d["ecr"] = ecr.reindex(ids)
    d["team_games"] = team_games
    d["bpv_total"] = d.bpv_fpg * d.p_hat * team_games
    d["espn_total"] = d.espn_fpg * d.espn_gp

    # Baseline: the app's preseason blend (veterans with an ESPN projection), else BPV, else ESPN alone.
    vet = (d.prev_mpg >= 15) & d.espn_fpg.notna() & (d.espn_gp > 0) & d.bpv_fpg.notna()
    d["base_fpg"] = np.where(vet, (1 - ratings.ESPN_FPG_WEIGHT) * d.bpv_fpg + ratings.ESPN_FPG_WEIGHT * d.espn_fpg,
                             d.bpv_fpg.fillna(d.espn_fpg))
    d["base_gp"] = np.where(vet, np.minimum(d.espn_gp * ratings.ESPN_GAMES_SCALE, team_games),
                            (d.p_hat * team_games).fillna(d.espn_gp * ratings.ESPN_GAMES_SCALE))
    d["base_total"] = (d.base_fpg * d.base_gp).fillna(0)

    # Actual results (0 points if he didn't play).
    d["act_total"] = h_t.fpts_total.reindex(ids).fillna(0)
    d["act_games"] = h_t.played.reindex(ids).fillna(0)
    d["act_fpg"] = np.where(d.act_games >= 20, h_t.fpts_pg.reindex(ids), np.nan)
    d["act_mpg"] = h_t.mpg.reindex(ids)

    # Slices for the decomposition.
    ages = nba_data.player_ages(prev).set_index("PLAYER_ID").AGE.reindex(ids) + 1
    d["age"] = ages
    d["team_changer"] = ctx.changed.reindex(ids).fillna(0).astype(bool) & d.bpv_fpg.notna()
    d["injury_news"] = d.espn_gp < 60
    d["second_year"] = d.index.isin(debuts[prev])
    d["young"] = d.age <= 23
    d["old"] = d.age >= 32

    # Fixed pool: union of top 150s (baseline, ESPN, ECR) and actual top 150.
    top = lambda s: set(s.sort_values(ascending=False).head(150).index)
    pool = top(d.base_total) | top(d.espn_total.dropna()) | set(d.ecr[d.ecr <= 150].index) | top(d.act_total)
    d["in_pool"] = d.index.isin(pool)
    d["act_top50"] = d.index.isin(d.act_total.sort_values(ascending=False).head(50).index)
    return d


# ---------------------------------------------------------------- ECR -> points curves (LOSO)
def pav_decreasing(x, y):
    """Isotonic (non-increasing) fit of y on sorted x; returns fitted values aligned to x order."""
    order = np.argsort(x)
    yv = [[float(v), 1.0] for v in np.asarray(y, float)[order]]
    blocks = []
    for v, w in yv:
        blocks.append([v, w, 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            v2, w2, n2 = blocks.pop()
            v1, w1, n1 = blocks.pop()
            blocks.append([(v1 * w1 + v2 * w2) / (w1 + w2), w1 + w2, n1 + n2])
    fitted = np.concatenate([[v] * n for v, _, n in blocks])
    out = np.empty(len(fitted))
    out[order] = fitted
    return out


def ecr_curve(train, col):
    """rank -> expected value, pooled over training seasons (ranks 1..300)."""
    t = train[train.ecr.notna() & (train.ecr <= 300)]
    t = t.dropna(subset=[col])
    x, y = t.ecr.to_numpy(float), t[col].to_numpy(float)
    fit = pav_decreasing(x, y)
    grid = np.arange(1, 301)
    df = pd.DataFrame({"x": x, "f": fit}).groupby("x").f.mean()
    vals = np.interp(grid, df.index.to_numpy(), df.to_numpy())
    return lambda r: np.interp(np.where(np.isnan(r), 300, np.minimum(r, 300)), grid, vals)


def add_ecr(frames):
    for t in SEASONS:
        train = pd.concat([frames[s] for s in SEASONS if s != t])
        tot, fpg = ecr_curve(train, "act_total"), ecr_curve(train, "act_fpg")
        f = frames[t]
        f["ecr_total"] = np.where(f.ecr.notna(), tot(f.ecr.to_numpy(float)), np.nan)
        f["ecr_fpg"] = np.where(f.ecr.notna(), fpg(f.ecr.to_numpy(float)), np.nan)


def weighted(f, cols, weights):
    vals = np.column_stack([f[c].to_numpy(float) for c in cols])
    w = np.array(weights, float)[None, :] * ~np.isnan(vals)
    return np.where(w.sum(1) > 0, np.nansum(vals * w, 1) / np.where(w.sum(1) > 0, w.sum(1), 1), 0.0)


# ---------------------------------------------------------------- scoring
def paired(d, var, base, target, mask=None):
    """Per-season wins and a player-clustered bootstrap of mean(|var-target| - |base-target|)."""
    m = d[target].notna() & (d.in_pool if mask is None else mask)
    x = d[m]
    diff = (x[var] - x[target]).abs() - (x[base] - x[target]).abs()
    by_season = diff.groupby(x.season).mean()
    players = x.index.to_numpy()
    uniq = np.unique(players)
    sums = pd.Series(diff.to_numpy()).groupby(players).agg(["sum", "count"])
    s, c = sums["sum"].reindex(uniq).to_numpy(), sums["count"].reindex(uniq).to_numpy()
    boots = []
    for _ in range(B):
        idx = RNG.integers(0, len(uniq), len(uniq))
        boots.append(s[idx].sum() / c[idx].sum())
    return {"mean_diff": float(diff.mean()), "ci95": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "boot": boots, "wins": int((by_season < 0).sum()), "by_season": {k: float(v) for k, v in by_season.items()},
            "n": int(len(x)), "mae_var": float((x[var] - x[target]).abs().mean()), "mae_base": float((x[base] - x[target]).abs().mean())}


def pvalue(boots):
    """Two-sided bootstrap p-value for mean < 0 (share of resamples on the wrong side, doubled)."""
    b = np.asarray(boots)
    return float(min(1.0, 2 * min((b >= 0).mean(), (b <= 0).mean())))


def spearman(d, col):
    out = {}
    for t, g in d[d.in_pool].groupby("season"):
        out[t] = float(g[col].rank().corr(g.act_total.rank()))
    return float(np.mean(list(out.values())))


def design_b(frames, cols):
    """Gain in best-10 FPTS vs an ESPN-drafting team from the same seat, averaged over seats and seasons."""
    res = {c: [] for c in cols}
    for t in SEASONS:
        f = frames[t]
        actual = f.act_total.to_dict()
        rankings = {c: f[c].fillna(-math.inf).sort_values(ascending=False, kind="stable").index.tolist() for c in cols}
        rankings["ESPN"] = f.espn_total.fillna(-math.inf).sort_values(ascending=False, kind="stable").index.tolist()
        g = pr.vs_field(rankings, "ESPN", actual)
        for c in cols:
            res[c].append(g[c]["gain_best10"])
    return {c: {"mean": float(np.mean(v)), "by_season": [float(x) for x in v]} for c, v in res.items()}


def verdicts(results, keys):
    """Holm correction over the adoption candidates; adoption rule from the pre-registration."""
    ps = sorted(((pvalue(results[k]["boot"]), k) for k in keys))
    m, out, blocked = len(ps), {}, False
    for i, (p, k) in enumerate(ps):
        r = results[k]
        holm_ok = (not blocked) and p <= 0.05 / (m - i) and r["mean_diff"] < 0
        if not holm_ok:
            blocked = True
        out[k] = {"p": p, "holm_pass": holm_ok, "wins": r["wins"], "top50_ok": r["top50_diff"] <= 0,
                  "adopt": holm_ok and r["wins"] >= 3 and r["top50_diff"] <= 0}
    return out


def strip(r):
    return {k: v for k, v in r.items() if k != "boot"}


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    frames = {t: season_data(pg, tg, hist, league_p, league_q, t, names, debuts) for t in SEASONS}
    add_ecr(frames)
    res = {"pool": {t: int(frames[t].in_pool.sum()) for t in SEASONS}}

    # ---- item 1
    for f in frames.values():
        f["v1B"] = weighted(f, ["bpv_total", "espn_total", "ecr_total"], [1, 1, 1])
        f["v1C"] = weighted(f, ["bpv_total", "espn_total", "ecr_total"], [0.25, 0.25, 0.5])
        f["ecr_only"] = f.ecr_total
        # per-game versions, for the secondary metric
        f["v1B_fpg"] = weighted(f, ["bpv_fpg", "espn_fpg", "ecr_fpg"], [1, 1, 1])
        f["v1C_fpg"] = weighted(f, ["bpv_fpg", "espn_fpg", "ecr_fpg"], [0.25, 0.25, 0.5])
    d = pd.concat(frames.values())
    item1 = {}
    for v in ("v1B", "v1C"):
        r = paired(d, v, "base_total", "act_total")
        r["top50_diff"] = paired(d, v, "base_total", "act_total", mask=d.act_top50)["mean_diff"]
        r["per_game"] = strip(paired(d, v + "_fpg", "base_fpg", "act_fpg"))
        r["spearman"] = spearman(d, v)
        item1[v] = r
    item1["ecr_alone_vs_base"] = strip(paired(d.assign(e=d.ecr_total.fillna(0)), "e", "base_total", "act_total"))
    item1["spearman_base"] = spearman(d, "base_total")
    item1["design_b"] = design_b(frames, ["base_total", "v1B", "v1C"])

    # ---- item 2 (diagnostic): where does ECR beat the baseline?
    d["ecr_gp"] = d.ecr_total / d.ecr_fpg
    decomp = {}
    slices = {"all": d.in_pool, "team_changer": d.in_pool & d.team_changer, "injury_news": d.in_pool & d.injury_news,
              "second_year": d.in_pool & d.second_year, "age<=23": d.in_pool & d.young, "age>=32": d.in_pool & d.old,
              "actual_top50": d.act_top50}
    for name, m in slices.items():
        x = d[m & d.ecr_total.notna()]
        e_base = (x.base_total - x.act_total).abs()
        e_ecr = (x.ecr_total - x.act_total).abs()
        pgm = x.act_fpg.notna()
        decomp[name] = {"n": int(len(x)), "total_err_base": float(e_base.mean()), "total_err_ecr": float(e_ecr.mean()),
                        "ecr_minus_base_total": float((e_ecr - e_base).mean()),
                        "fpg_err_base": float((x.base_fpg - x.act_fpg).abs()[pgm].mean()),
                        "fpg_err_ecr": float((x.ecr_fpg - x.act_fpg).abs()[pgm].mean()),
                        "games_err_base": float((x.base_gp - x.act_games).abs().mean()),
                        "games_err_ecr": float((x.ecr_gp - x.act_games).abs().mean())}
    res["item2_decomposition"] = decomp

    # ---- item 3: minutes from ESPN, rate from BPV
    for f in frames.values():
        rate = f.bpv_fpg / f.prev_mpg
        ok = f.espn_min.notna() & rate.notna() & (f.prev_mpg >= 10)
        f["v3B_fpg"] = np.where(ok, rate * f.espn_min, f.base_fpg)
        f["v3C_fpg"] = np.where(ok, rate * (0.5 * f.prev_mpg + 0.5 * f.espn_min), f.base_fpg)
        f["v3B"] = (f.v3B_fpg * f.base_gp).fillna(0)
        f["v3C"] = (f.v3C_fpg * f.base_gp).fillna(0)
    d = pd.concat(frames.values())
    item3 = {}
    for v in ("v3B", "v3C"):
        r = paired(d, v + "_fpg", "base_fpg", "act_fpg")
        r["top50_diff"] = paired(d, v + "_fpg", "base_fpg", "act_fpg", mask=d.act_top50)["mean_diff"]
        r["totals"] = strip(paired(d, v, "base_total", "act_total"))
        item3[v] = r
    # Does the minutes part improve? (ESPN minutes vs last season's, against actual minutes)
    mm = d[d.in_pool & d.espn_min.notna() & d.prev_mpg.notna() & d.act_mpg.notna() & (d.act_games >= 20)]
    item3["minutes_mae"] = {"last_season": float((mm.prev_mpg - mm.act_mpg).abs().mean()),
                            "espn": float((mm.espn_min - mm.act_mpg).abs().mean()), "n": int(len(mm))}

    # ---- decide items 1 and 3 together (Holm over all candidates in this script)
    cands = {"1B": item1["v1B"], "1C": item1["v1C"], "3B": item3["v3B"], "3C": item3["v3C"]}
    v = verdicts(cands, list(cands))
    res["verdicts_1_3"] = v

    # ---- item 4: slice weights on outside sources, chosen LOSO
    win1 = next((k for k in ("1C", "1B") if v[k]["adopt"]), None)
    outside_cols, outside_w = (["espn_total", "ecr_total"], [1, 1]) if win1 == "1B" else \
        (["espn_total", "ecr_total"], [1, 2]) if win1 == "1C" else (["espn_total"], [1])
    base_w = {"1B": 2 / 3, "1C": 0.75, None: ratings.ESPN_FPG_WEIGHT}[win1]
    ref = {"1B": "v1B", "1C": "v1C", None: "base_total"}[win1]
    for f in frames.values():
        f["outside"] = weighted(f, outside_cols, outside_w)
        f["own"] = f.bpv_total
    grid = [0, 0.15, 0.30]
    slices4 = ["team_changer", "second_year", "injury_news"]

    def proj(f, bumps):
        w = np.full(len(f), base_w)
        for s, b in zip(slices4, bumps):
            w = np.where(f[s], np.minimum(1, w + b), w)
        own_ok = f.own.notna()
        mixed = np.where(own_ok, (1 - w) * f.own.fillna(0) + w * f.outside, f.outside)
        # Players outside every slice keep the reference projection exactly.
        any_slice = f[slices4].any(axis=1)
        return np.where(any_slice, mixed, f[ref])

    for t in SEASONS:
        train = pd.concat([frames[s] for s in SEASONS if s != t])
        best, best_err = None, None
        for b1 in grid:
            for b2 in grid:
                for b3 in grid:
                    p = proj(train, (b1, b2, b3))
                    m = train.in_pool.to_numpy()
                    err = np.abs(p[m] - train.act_total.to_numpy()[m]).mean()
                    if best_err is None or err < best_err:
                        best, best_err = (b1, b2, b3), err
        frames[t]["v4"] = proj(frames[t], best)
        frames[t]["v4_bumps"] = str(best)
    d = pd.concat(frames.values())
    r4 = paired(d, "v4", ref, "act_total")
    r4["top50_diff"] = paired(d, "v4", ref, "act_total", mask=d.act_top50)["mean_diff"]
    r4["bumps_by_season"] = {t: frames[t].v4_bumps.iloc[0] for t in SEASONS}
    r4["reference"] = ref
    res["item4"] = strip(r4)
    res["verdict_4"] = verdicts({"4": r4}, ["4"])

    res["item1"] = {k: (strip(val) if isinstance(val, dict) and "boot" in val else val) for k, val in item1.items()}
    res["item3"] = {k: (strip(val) if isinstance(val, dict) and "boot" in val else val) for k, val in item3.items()}
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
