"""Round 10, items 5 and 7 (docs/prereg-round10.md): fitted per-stat rates, and per-stat aging.

Run:  python -m analysis.round10_rates        (writes analysis/round10_rates.json)

Per-minute rate of each scoring stat = (sum of w*stat + k*league rate) / (sum of w*minutes + k), with
w = 0.5 ** (days before the target season's first game / half_life). half_life and k are fitted per stat
by grid search against the next season's per-minute rate (minute-weighted squared error) on targets
2012-13..2018-19, never on the scored seasons. FPTS rate = ESPN-scoring-weighted sum of the stat rates.
"""
import json
import os
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
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "round10_rates.json")
STATS = ["PTS", "FG3M", "FGA", "FGM", "FTA", "FTM", "REB", "AST", "STL", "BLK", "TOV"]
ALL = [nba_data.season_string(y) for y in range(2009, 2026)]
FIT_TARGETS = [nba_data.season_string(y) for y in range(2012, 2019)]
AGE_FIT_PAIRS = [(nba_data.season_string(y), nba_data.season_string(y + 1)) for y in range(2010, 2018)]
HALF_LIVES = [60, 120, 200, 365, 550, 730, 1100, 1500, 2500]
PADS = [0, 50, 100, 200, 400, 800, 1500, 3000]
HISTORY = 3          # seasons of history used


def load_all():
    return {s: nba_data.player_game_logs(s) for s in ALL}


def weighted_sums(pg, target, half_life):
    """Per player: decay-weighted sums of each stat and minutes over the HISTORY seasons before target."""
    i = ALL.index(target)
    start = pd.Timestamp(pg[target].GAME_DATE.min())
    frames = [pg[s] for s in ALL[max(0, i - HISTORY):i]]
    g = pd.concat(frames)
    days = (start - pd.to_datetime(g.GAME_DATE)).dt.days.to_numpy(float)
    w = 0.5 ** (days / half_life)
    cols = STATS + ["MIN"]
    out = pd.DataFrame(g[cols].to_numpy(float) * w[:, None], columns=cols)
    out["PLAYER_ID"] = g.PLAYER_ID.to_numpy()
    return out.groupby("PLAYER_ID").sum()


def league_rates(pg, season):
    g = pg[season]
    return {s: g[s].sum() / g.MIN.sum() for s in STATS}


def season_rates(pg, season, min_minutes):
    g = pg[season].groupby("PLAYER_ID")[STATS + ["MIN"]].sum()
    g = g[g.MIN >= min_minutes]
    return g[STATS].div(g.MIN, axis=0), g.MIN


def fit_constants(pg):
    """Per stat: (half_life, pad) minimising minute-weighted squared error on FIT_TARGETS."""
    sums = {(t, h): weighted_sums(pg, t, h) for t in FIT_TARGETS for h in HALF_LIVES}
    actual = {t: season_rates(pg, t, 500) for t in FIT_TARGETS}
    lg = {t: league_rates(pg, ALL[ALL.index(t) - 1]) for t in FIT_TARGETS}
    best = {}
    for s in STATS:
        scores = {}
        for h in HALF_LIVES:
            for k in PADS:
                num, den = 0.0, 0.0
                for t in FIT_TARGETS:
                    ws = sums[(t, h)]
                    rates, mins = actual[t]
                    ids = rates.index.intersection(ws.index[ws.MIN > 0])
                    pred = (ws.loc[ids, s] + k * lg[t][s]) / (ws.loc[ids, "MIN"] + k)
                    err = (pred - rates.loc[ids, s]) ** 2
                    num += float((err * mins.loc[ids]).sum())
                    den += float(mins.loc[ids].sum())
                scores[(h, k)] = num / den
        (h, k) = min(scores, key=scores.get)
        best[s] = {"half_life_days": h, "pad_minutes": k}
    return best


def component_rates(pg, target, consts):
    lg = league_rates(pg, ALL[ALL.index(target) - 1])
    out = {}
    for s in STATS:
        h, k = consts[s]["half_life_days"], consts[s]["pad_minutes"]
        ws = weighted_sums(pg, target, h)
        ws = ws[ws.MIN > 0]
        out[s] = (ws[s] + k * lg[s]) / (ws.MIN + k)
    return pd.DataFrame(out)


def fpts_rate(rates):
    return sum(rates[s] * w for s, w in bpv.SCORING.items())


def age_deltas(pg):
    """Mean change in each stat's per-minute rate from one season to the next, by age bucket (minute-weighted)."""
    rows = []
    for a, b in AGE_FIT_PAIRS:
        ra, ma = season_rates(pg, a, 500)
        rb, mb = season_rates(pg, b, 500)
        ids = ra.index.intersection(rb.index)
        ages = nba_data.player_ages(a).set_index("PLAYER_ID").AGE.reindex(ids)
        d = (rb.loc[ids] - ra.loc[ids])
        d["bucket"] = ages.map(lambda x: bpv.age_bucket(x) if pd.notna(x) else None)
        d["w"] = np.minimum(ma.loc[ids], mb.loc[ids])
        rows.append(d.dropna(subset=["bucket"]))
    d = pd.concat(rows)
    return {bk: {s: float((g[s] * g.w).sum() / g.w.sum()) for s in STATS} for bk, g in d.groupby("bucket")}


def main():
    pg_all = load_all()
    consts = fit_constants(pg_all)
    deltas = age_deltas(pg_all)
    print("constants", json.dumps(consts), flush=True)

    # Scored seasons: reuse round 10's frames (baseline blend, pool, actuals).
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    frames = {}
    for t in r10.SEASONS:
        f = r10.season_data(pg, tg, hist, league_p, league_q, t, names, debuts)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        h_prev = hist[hist.season == prev].set_index("PLAYER_ID")
        s_prev = h_prev.fpts_pg.reindex(f.index)
        adj = f.bpv_fpg - s_prev                          # BPV's age + crowding adjustment, FPTS/game
        comp = component_rates(pg_all, t, consts)
        rate_b = fpts_rate(comp).reindex(f.index)
        ages = nba_data.player_ages(prev).set_index("PLAYER_ID").AGE.reindex(f.index)
        age_part = ages.map(lambda a: sum(deltas.get(bpv.age_bucket(a), {}).get(s, 0) * w for s, w in bpv.SCORING.items())
                            if pd.notna(a) else 0.0)
        f["rate_A"] = f.bpv_fpg / f.prev_mpg
        f["rate_B"] = rate_b + adj / f.prev_mpg
        # 5C: per-stat aging instead of the total age curve. Remove the total age part from adj.
        age_total = bt.age_curve_before(pg, t)
        age_adj = ages.map(lambda a: age_total.get(bpv.age_bucket(a), 0.0) if pd.notna(a) else 0.0)
        eligible = (f.prev_mpg >= 15) & ages.notna()
        age_adj = age_adj.where(eligible, 0.0)
        f["rate_C"] = rate_b + age_part.where(eligible, 0.0) + (adj - age_adj) / f.prev_mpg
        ok = f.bpv_fpg.notna() & f.prev_mpg.notna() & (f.prev_mpg >= 10) & rate_b.notna()
        for v in ("A", "B", "C"):
            f[f"minfix_{v}"] = np.where(ok, f[f"rate_{v}"] * f.act_mpg, np.nan)       # minutes held at actual
            f[f"own_{v}"] = np.where(ok, f[f"rate_{v}"] * f.prev_mpg, np.nan)         # full own projection
            vet = ok & (f.prev_mpg >= 15) & f.espn_fpg.notna() & (f.espn_gp > 0)
            f[f"blend_{v}"] = np.where(vet, (1 - ratings.ESPN_FPG_WEIGHT) * f[f"own_{v}"] + ratings.ESPN_FPG_WEIGHT * f.espn_fpg,
                                       np.where(ok, f[f"own_{v}"], f.base_fpg))
        f["cmp"] = ok
        frames[t] = f
    d = pd.concat(frames.values())
    d = d[d.cmp]
    res = {"constants": consts, "age_deltas_fpts_per_min": {b: sum(v[s] * w for s, w in bpv.SCORING.items()) for b, v in deltas.items()}}
    for v in ("B", "C"):
        block = {}
        block["rate_side_minutes_at_actual"] = r10.strip(r10.paired(d, f"minfix_{v}", "minfix_A", "act_fpg"))
        block["own_projection"] = r10.strip(r10.paired(d, f"own_{v}", "own_A", "act_fpg"))
        r = r10.paired(d, f"blend_{v}", "blend_A", "act_fpg")
        r["top50_diff"] = r10.paired(d, f"blend_{v}", "blend_A", "act_fpg", mask=d.act_top50)["mean_diff"]
        block["in_app_blend"] = r10.strip(r)
        block["verdict"] = r10.verdicts({v: r}, [v])[v]
        res[f"5{v}"] = block
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
