"""Candidate BPV improvements: teammate absences, per-stat recency, per-stat age curves.

Run:  python -m analysis.test_teammates_perstat

TEST 1  In-season, game level. Does a player's FPTS (and minutes) rise when high-minute
        teammates sit? Baseline = season-to-date FPTS/game. Fitted on bt.TRAIN, scored on bt.TEST.
TEST 2  In-season, rest-of-season target. Separate recency weight per ESPN scoring component
        vs the current minutes/efficiency split (0.3 / 0.1). Fitted on bt.TRAIN, scored on bt.TEST.
TEST 3  Preseason. Per-component age-bucket adjustment vs the FPTS-level adjustment,
        leave-one-season-out on analysis.preseason_production's frame.
All comparisons: mean difference in absolute error, 95% bootstrap interval resampling players.
"""
import datetime as dt
from bisect import bisect_left

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import preseason_production as pp

RNG = np.random.default_rng(11)
N_BOOT = 1000
COMP = ["PTS", "REB", "AST", "STL", "BLK", "TOV", "SHOOT"]
W = {"PTS": 1, "REB": 1, "AST": 2, "STL": 4, "BLK": 4, "TOV": -2, "SHOOT": 1}


def add_components(g):
    g = g.copy()
    g["SHOOT"] = 2 * g.FGM - g.FGA + g.FTM - g.FTA + g.FG3M
    recon = sum(W[c] * g[c] for c in COMP)
    assert np.allclose(recon, g.FPTS), "component weights do not reproduce FPTS"
    return g


def boot(pids, err_new, err_old, n=N_BOOT):
    """Mean of (|new| - |old|) and a 95% interval resampling players (all their rows together)."""
    d = pd.DataFrame({"p": np.asarray(pids), "d": np.asarray(err_new) - np.asarray(err_old)})
    agg = d.groupby("p").d.agg(["sum", "size"])
    s, c = agg["sum"].to_numpy(), agg["size"].to_numpy()
    idx = RNG.integers(0, len(s), size=(n, len(s)))
    draws = s[idx].sum(1) / c[idx].sum(1)
    return float(d.d.mean()), [float(x) for x in np.percentile(draws, [2.5, 97.5])]


def verdict(diff, ci):
    if ci[1] < 0:
        return "better (CI excludes 0)"
    if ci[0] > 0:
        return "worse (CI excludes 0)"
    return "tie"


def show(label, pids, new, old, actual):
    en, eo = np.abs(new - actual), np.abs(old - actual)
    d, ci = boot(pids, en, eo)
    print(f"  {label:<48s} MAE {en.mean():.4f} vs {eo.mean():.4f}  diff {d:+.4f} "
          f"[{ci[0]:+.4f}, {ci[1]:+.4f}]  {verdict(d, ci)}")
    return d, ci


# ======================================================================= TEST 1
def game_rows(season, g, tg):
    """Every player-game with season-to-date baseline and missing-teammate minutes."""
    g = g.sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True)
    grp = g.groupby("PLAYER_ID")
    g["n_prior"] = grp.cumcount()
    g["cum_fp"] = grp.FPTS.cumsum() - g.FPTS          # before this game
    g["cum_min"] = grp.MIN.cumsum() - g.MIN
    players = {}
    for pid, h in g.groupby("PLAYER_ID"):
        players[pid] = (h.GAME_DATE.tolist(), h.TEAM_ID.tolist(), np.r_[0.0, h.MIN.cumsum().to_numpy()])
    roster = g.groupby("TEAM_ID").PLAYER_ID.unique()
    missing = {}   # (team, date) -> missing minutes
    for team, dates in tg.groupby("TEAM_ID").GAME_DATE:
        cands = roster.get(team, [])
        for d in sorted(set(dates)):
            m = 0.0
            for p in cands:
                pd_, pt, cmin = players[p]
                i = bisect_left(pd_, d)
                if i < 10 or pt[i - 1] != team:           # >=10 prior games, last seen on this team
                    continue
                if i < len(pd_) and pd_[i] == d:          # he played
                    continue
                if i < len(pd_) and pt[i] != team:        # traded away (next game is for another team)
                    continue
                mpg = cmin[i] / i
                if mpg >= 20:
                    m += mpg
            missing[(team, d)] = m
    g["M"] = [missing.get((t, d), 0.0) for t, d in zip(g.TEAM_ID, g.GAME_DATE)]
    grp = g.groupby("PLAYER_ID")
    g["M_prior_avg"] = (grp.M.cumsum() - g.M) / g.n_prior.clip(lower=1)
    g = g[g.n_prior >= 10].copy()
    g["S"] = g.cum_fp / g.n_prior
    g["mpg_S"] = g.cum_min / g.n_prior
    g = g[g.mpg_S >= 15].copy()
    g["fpm_S"] = g.S / g.mpg_S
    g["season"] = season
    return g[["season", "PLAYER_ID", "GAME_DATE", "TEAM_ID", "FPTS", "MIN", "S", "mpg_S", "fpm_S", "M", "M_prior_avg"]]


def lsq(X, y):
    X = np.column_stack(X) if isinstance(X, (list, tuple)) else np.asarray(X).reshape(len(y), -1)
    return np.linalg.lstsq(X, y, rcond=None)[0]


def test1(pg, tg):
    print("\n=== TEST 1: teammate absences (game level) ===")
    rows = pd.concat([game_rows(s, pg[s], tg[s]) for s in bt.TRAIN + bt.TEST], ignore_index=True)
    rows["dM"] = rows.M - rows.M_prior_avg
    tr, te = rows[rows.season.isin(bt.TRAIN)], rows[rows.season.isin(bt.TEST)]
    print(f"rows train {len(tr)}, test {len(te)}; test players {te.PLAYER_ID.nunique()}")
    print(f"share of games with any missing teammate: train {np.mean(tr.M > 0):.3f}, test {np.mean(te.M > 0):.3f}; "
          f"mean M | M>0: {tr.M[tr.M > 0].mean():.1f} min")
    y, ym = (tr.FPTS - tr.S).to_numpy(), (tr.MIN - tr.mpg_S).to_numpy()
    one = np.ones(len(tr))
    feats = {
        "V1 b*M": lambda d: [d.M],
        "V2 b*M*fpm_S": lambda d: [d.M * d.fpm_S],
        "V3 b*dM (M minus player's prior avg M)": lambda d: [d.dM],
        "V4 b*dM*fpm_S": lambda d: [d.dM * d.fpm_S],
    }
    coefs = {}
    for k, f in feats.items():
        b = lsq(f(tr), y)[0]
        bm = lsq(f(tr), ym)[0]
        coefs[k] = b
        print(f"{k}: FPTS coef {b:.4f}, minutes coef {bm:.4f}")
    print(f"effect per 10 missing teammate minutes (V1): {10 * coefs['V1 b*M']:+.2f} FPTS, "
          f"{10 * lsq([tr.M], ym)[0]:+.2f} min; mean fpm_S train {tr.fpm_S.mean():.3f}")
    # Binned check (train): raw mean residual by M bucket.
    bins = pd.cut(tr.M, [-0.1, 0.1, 25, 40, 60, 200])
    print("train mean residual by missing-minutes bin:")
    print(pd.DataFrame({"n": tr.groupby(bins, observed=True).size(),
                        "FPTS-S": pd.Series(y, tr.index).groupby(bins, observed=True).mean(),
                        "MIN-mpg": pd.Series(ym, tr.index).groupby(bins, observed=True).mean()}).round(3))
    intercept = y.mean()
    print(f"intercept-only drift (train mean FPTS-S): {intercept:+.3f}")
    base = te.S.to_numpy()
    act, pids = te.FPTS.to_numpy(), te.PLAYER_ID.to_numpy()
    print("TEST game-level MAE (new vs season-to-date baseline):")
    show("intercept only", pids, base + intercept, base, act)
    for k, f in feats.items():
        show(k, pids, base + coefs[k] * f(te)[0].to_numpy(), base, act)
    # Best variant with intercept, vs intercept only (isolates the teammate term).
    X = np.column_stack([one, tr.M * tr.fpm_S])
    a, b = lsq(X, y)
    pred = base + a + b * (te.M * te.fpm_S).to_numpy()
    print(f"V2 with intercept: a={a:+.3f}, b={b:.4f}")
    show("V2+intercept vs intercept only", pids, pred, base + intercept, act)
    # Only the games where something is missing.
    mask = (te.M > 0).to_numpy()
    show("V2 vs baseline, games with M>0 only", pids[mask], base[mask] + coefs["V2 b*M*fpm_S"] *
         (te.M * te.fpm_S).to_numpy()[mask], base[mask], act[mask])
    # Minutes MAE
    bm = lsq([tr.M], ym)[0]
    show("minutes: mpg_S + b*M vs mpg_S", pids, te.mpg_S.to_numpy() + bm * te.M.to_numpy(), te.mpg_S.to_numpy(),
         te.MIN.to_numpy())


# ======================================================================= TEST 2
def comp_checkpoint_rows(season, g, first_offset_days=28, min_before=10, min_after=10):
    cps = bt.checkpoints(g, first_offset_days)
    rows = []
    for pid, h in g.groupby("PLAYER_ID"):
        h = h.sort_values("GAME_DATE")
        dates = h.GAME_DATE.tolist()
        vals = h[COMP + ["FPTS", "MIN"]].to_numpy(float)
        for c in cps:
            i = bisect_left(dates, c)
            if i < min_before or len(dates) - i < min_after:
                continue
            S, L5, A = vals[:i].mean(0), vals[max(0, i - bt.RECENT_GAMES):i].mean(0), vals[i:].mean(0)
            r = {"season": season, "checkpoint": c, "PLAYER_ID": pid}
            for k, col in enumerate(COMP + ["FPTS", "MIN"]):
                r[f"S_{col}"], r[f"L_{col}"], r[f"A_{col}"] = S[k], L5[k], A[k]
            rows.append(r)
    return pd.DataFrame(rows)


def split_pred(d, wm=0.3, we=0.1):
    fpm = d.S_FPTS / d.S_MIN.clip(lower=1)
    dmin = fpm * (d.L_MIN - d.S_MIN)
    deff = d.L_FPTS - d.S_FPTS - dmin
    return d.S_FPTS + wm * dmin + we * deff


def test2(pg, tg):
    print("\n=== TEST 2: per-stat recency (rest-of-season FPTS/game) ===")
    cp = pd.concat([comp_checkpoint_rows(s, pg[s]) for s in bt.TRAIN + bt.TEST], ignore_index=True)
    cp = cp[cp.S_MIN >= 12]
    # Sanity: same row count as bt.checkpoint_rows would give (same rules).
    tr, te = cp[cp.season.isin(bt.TRAIN)], cp[cp.season.isin(bt.TEST)]
    print(f"rows train {len(tr)}, test {len(te)}; test players {te.PLAYER_ID.nunique()}")
    w = {}
    for c in COMP:
        x, y = tr[f"L_{c}"] - tr[f"S_{c}"], tr[f"A_{c}"] - tr[f"S_{c}"]
        w[c] = float((x * y).sum() / (x * x).sum())
    x, y = tr.L_FPTS - tr.S_FPTS, tr.A_FPTS - tr.S_FPTS
    w_fp = float((x * y).sum() / (x * x).sum())
    print("per-component recent weights (train LS):", {k: round(v, 3) for k, v in w.items()}, f"| single FPTS weight {w_fp:.3f}")
    # Refit the split on train for reference.
    fpm = tr.S_FPTS / tr.S_MIN.clip(lower=1)
    dmin = fpm * (tr.L_MIN - tr.S_MIN)
    wm, we = lsq([dmin, tr.L_FPTS - tr.S_FPTS - dmin], (tr.A_FPTS - tr.S_FPTS).to_numpy())
    print(f"split refit on train: minutes {wm:.3f}, efficiency {we:.3f} (current 0.3 / 0.1)")

    def per_comp(d, weights):
        return sum(W[c] * (d[f"S_{c}"] + weights[c] * (d[f"L_{c}"] - d[f"S_{c}"])) for c in COMP)

    # Per-component minutes/efficiency split: each component = rate * minutes.
    comp_split = {}
    for c in COMP:
        r = tr[f"S_{c}"] / tr.S_MIN.clip(lower=1)
        dm = r * (tr.L_MIN - tr.S_MIN)
        de = tr[f"L_{c}"] - tr[f"S_{c}"] - dm
        comp_split[c] = lsq([dm, de], (tr[f"A_{c}"] - tr[f"S_{c}"]).to_numpy())
    print("per-component split (minutes, efficiency) weights:", {k: tuple(np.round(v, 3)) for k, v in comp_split.items()})

    def per_comp_split(d):
        out = 0
        for c in COMP:
            r = d[f"S_{c}"] / d.S_MIN.clip(lower=1)
            dm = r * (d.L_MIN - d.S_MIN)
            de = d[f"L_{c}"] - d[f"S_{c}"] - dm
            out = out + W[c] * (d[f"S_{c}"] + comp_split[c][0] * dm + comp_split[c][1] * de)
        return out

    assert np.allclose(sum(W[c] * te[f"S_{c}"] for c in COMP), te.S_FPTS)
    base = split_pred(te).to_numpy()
    act, pids = te.A_FPTS.to_numpy(), te.PLAYER_ID.to_numpy()
    print(f"TEST MAE season-only {np.mean(np.abs(te.S_FPTS - act)):.4f}; current split {np.mean(np.abs(base - act)):.4f}")
    show("per-component recency vs current split", pids, per_comp(te, w).to_numpy(), base, act)
    show("per-comp minutes/eff split vs current split", pids, per_comp_split(te).to_numpy(), base, act)
    show("single FPTS weight (train) vs current split", pids, (te.S_FPTS + w_fp * (te.L_FPTS - te.S_FPTS)).to_numpy(), base, act)
    show("split refit on train vs current 0.3/0.1", pids, split_pred(te, wm, we).to_numpy(), base, act)


# ======================================================================= TEST 3
def comp_table(pg):
    out = []
    for s, g in pg.items():
        t = add_components(g).groupby("PLAYER_ID")[COMP].mean().reset_index()
        t["season"] = s
        out.append(t)
    return pd.concat(out, ignore_index=True)


def test3(pg):
    print("\n=== TEST 3: per-stat age curves (preseason, leave-one-season-out) ===")
    tab = pp.season_table(pg)
    ct = comp_table(pg)
    frames = []
    for t in pp.TARGETS:
        f = pp.frame(tab, t)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        p = ct[ct.season == prev].set_index("PLAYER_ID")[COMP].add_prefix("P_")
        a = ct[ct.season == t].set_index("PLAYER_ID")[COMP].add_prefix("A_")
        f = f.join(p, on="PLAYER_ID").join(a, on="PLAYER_ID")
        frames.append(f)
    df = pd.concat(frames, ignore_index=True)
    n_nan_age = int(df.age.isna().sum())
    print(f"rows {len(df)}, players {df.PLAYER_ID.nunique()}, missing age {n_nan_age} (adjustment 0 for those)")
    assert np.allclose(sum(W[c] * df[f"P_{c}"] for c in COMP), df.fp1)
    df["bucket"] = df.age.map(lambda a: pp.age_bucket(a) if pd.notna(a) else None)
    out = []
    for t in pp.TARGETS:
        tr, te = df[(df.target != t) & df.bucket.notna()], df[df.target == t].copy()
        b = tr.bucket
        curve = (tr.actual - tr.fp1).groupby(b).mean()
        te["a"] = te.fp1 + te.bucket.map(curve).fillna(0)
        te["b"] = sum(W[c] * (te[f"P_{c}"] + te.bucket.map((tr[f"A_{c}"] - tr[f"P_{c}"]).groupby(b).mean()).fillna(0))
                      for c in COMP)
        # Multiplicative versions (differ from each other because players' stat mixes differ).
        ratio = tr.groupby(b).actual.sum() / tr.groupby(b).fp1.sum()
        te["a_mult"] = te.fp1 * te.bucket.map(ratio).fillna(1)
        # SHOOT averages near zero (can be negative), so a ratio is unstable: keep it additive.
        te["b_mult"] = sum(W[c] * (te[f"P_{c}"] + te.bucket.map((tr[f"A_{c}"] - tr[f"P_{c}"]).groupby(b).mean()).fillna(0))
                           if c == "SHOOT" else
                           W[c] * te[f"P_{c}"] * te.bucket.map(tr.groupby(b)[f"A_{c}"].sum() / tr.groupby(b)[f"P_{c}"].sum()).fillna(1)
                           for c in COMP)
        if t == "2025-26":
            print("per-component additive age change, fit on 2022-23..2024-25 (per game):")
            print(pd.DataFrame({c: (tr[f"A_{c}"] - tr[f"P_{c}"]).groupby(b).mean() for c in COMP})
                  .assign(FPTS=curve).reindex(pp.AGE_BUCKETS).round(2))
            print("per-component multiplicative ratio:")
            print(pd.DataFrame({c: tr.groupby(b)[f"A_{c}"].sum() / tr.groupby(b)[f"P_{c}"].sum() for c in COMP})
                  .assign(FPTS=ratio).reindex(pp.AGE_BUCKETS).round(3))
        out.append(te)
    r = pd.concat(out, ignore_index=True)
    print(f"max |b - a| (additive; should be ~0 by linearity): {np.abs(r.b - r.a).max():.2e}")
    act, pids = r.actual.to_numpy(), r.PLAYER_ID.to_numpy()
    print(f"MAE last only {np.mean(np.abs(r.fp1 - act)):.4f}")
    show("(b) per-comp additive vs (a) FPTS additive", pids, r.b.to_numpy(), r.a.to_numpy(), act)
    print(f"prev-season SHOOT per game: mean {r.P_SHOOT.mean():.2f}, min {r.P_SHOOT.min():.2f}, max {r.P_SHOOT.max():.2f}")
    show("(b') per-comp multiplicative vs (a)", pids, r.b_mult.to_numpy(), r.a.to_numpy(), act)
    show("(b') per-comp multiplicative vs FPTS multiplicative", pids, r.b_mult.to_numpy(), r.a_mult.to_numpy(), act)


def main():
    pg, tg = bt.load()
    pg = {s: add_components(g) for s, g in pg.items()}
    test1(pg, tg)
    test2(pg, tg)
    test3(pg)


if __name__ == "__main__":
    main()
