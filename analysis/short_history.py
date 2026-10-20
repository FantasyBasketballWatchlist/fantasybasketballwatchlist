"""Players with a short or missing recent history (rules fixed beforehand in docs/prereg-short-history.md).

T1 pooled two seasons between seasons, T2 draft-slot shrinkage for almost no NBA history (between seasons and in
season), T3 pooled prior in season, T4 returners with the ESPN blend (listed only). Writes analysis/short_history.json.

    python -m analysis.short_history
"""
import datetime
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ["NBA_OFFLINE"] = "1"

import bpv   # noqa: E402
import nba_data   # noqa: E402
import ratings   # noqa: E402
from analysis import test_espn_projections as te   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "short_history.json")
ALL = [nba_data.season_string(y) for y in range(2009, 2026)]
TARGETS = [nba_data.season_string(y) for y in range(2011, 2026)]
DAYS = [14, 28, 42, 70, 100]
NO_OVERRIDES = {"injuries": {}, "role_changes": {}}
BOOT = 2000

pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in ALL}
tg = {s: nba_data.team_game_logs(s) for s in ALL}
draft = nba_data.draft_history()
picks = draft.drop_duplicates("PERSON_ID").set_index("PERSON_ID")["OVERALL_PICK"]
ages = {}
for s in ALL:
    try:
        ages[s] = nba_data.player_ages(s).set_index("PLAYER_ID")["AGE"]
    except Exception:
        ages[s] = pd.Series(dtype=float)
prev = lambda s: nba_data.previous_season(s)
by_player = {s: dict(tuple(pg[s].groupby("PLAYER_ID"))) for s in ALL}


def age_adj(season_ages, pid):
    a = season_ages.get(pid)
    return 0.0 if a is None or pd.isna(a) else ratings.AGE_CURVE[bpv.age_bucket(a)]


_baselines = {}


def baselines(target):
    """Draft-slot rookie baselines from the five seasons before `target`, as ratings.build computes them."""
    if target not in _baselines:
        y = nba_data.season_start_year(target)
        first = nba_data.season_start_year(ALL[0])          # the cache starts at 2009-10
        window = [nba_data.season_string(x) for x in range(max(y - 5, first), y)]
        hist = bpv.availability_history(window, {s: pg[s] for s in window}, {s: tg[s] for s in window}, draft)
        _baselines[target] = bpv.rookie_baselines(bpv.rookie_seasons(window, {s: pg[s] for s in window}, draft, hist))
    return _baselines[target]


def draft_prior(target, pid):
    b = baselines(target)
    return b.get(bpv.pick_bucket(picks.get(pid)), b["undrafted"])["fpts_per_game"]


def compare(df, new, old):
    a, w = df["actual"].to_numpy(), df["w"].to_numpy(float)
    e_new, e_old = w * np.abs(new - a), w * np.abs(old - a)
    s_new, s_old = w * (new - a) ** 2, w * (old - a) ** 2
    res = {"cases": int(len(df)), "players": int(df["player"].nunique()),
           "mae_new": float(e_new.sum() / w.sum()), "mae_old": float(e_old.sum() / w.sum()),
           "mse_new": float(s_new.sum() / w.sum()), "mse_old": float(s_old.sum() / w.sum()),
           "mean_pred_new": float((w * new).sum() / w.sum()), "mean_pred_old": float((w * old).sum() / w.sum()),
           "mean_actual": float((w * a).sum() / w.sum())}
    res["diff"] = res["mae_new"] - res["mae_old"]
    players = df["player"].to_numpy()
    uniq = np.unique(players)
    idx = {p: np.flatnonzero(players == p) for p in uniq}
    rng = np.random.default_rng(7)
    diffs = []
    for _ in range(BOOT):
        t = np.concatenate([idx[p] for p in rng.choice(uniq, len(uniq))])
        diffs.append((e_new[t].sum() - e_old[t].sum()) / w[t].sum())
    res["ci"] = [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))]
    by = {s: float((e_new[m].sum() - e_old[m].sum()) / w[m].sum()) for s in sorted(df["season"].unique())
          for m in [(df["season"] == s).to_numpy()]}
    res["by_season"] = {k: round(v, 3) for k, v in by.items()}
    better = sum(v < 0 for v in by.values())
    res["seasons_better"] = f"{better} of {len(by)}"
    res["passes"] = bool(res["ci"][1] < 0 and better >= 0.6 * len(by))
    return res


def between_seasons():
    t1, t2 = [], []
    for s in TARGETS:
        s1, s2 = prev(s), prev(prev(s))
        now = pg[s].groupby("PLAYER_ID").agg(n=("FPTS", "size"), fpg=("FPTS", "mean"))
        now = now[now["n"] >= 10]
        for pid, g1 in by_player[s1].items():
            n1 = len(g1)
            if not 1 <= n1 <= 19 or pid not in now.index:
                continue
            g2 = by_player[s2].get(pid)
            pooled = pd.concat([g2, g1]) if g2 is not None else g1
            row = {"season": s, "player": int(pid), "name": g1["PLAYER_NAME"].iloc[-1], "n_last": n1,
                   "actual": float(now.loc[pid, "fpg"]), "w": int(now.loc[pid, "n"]), "p0": float(g1["FPTS"].mean())}
            if len(pooled) >= 20:
                row["p1"] = float(pooled["FPTS"].mean()) + (age_adj(ages[s1], pid) if pooled["MIN"].mean() >= ratings.AGE_MIN_MPG else 0.0)
                row["p2"] = (float(g2["FPTS"].mean()) + (age_adj(ages[s2], pid) + age_adj(ages[s1], pid)) / 2
                             if g2 is not None and len(g2) >= 20 else np.nan)
                t1.append(row)
            else:
                row["p1"] = bpv.shrink(row["p0"], n1, draft_prior(s, pid), ratings.ROOKIE_K)
                t2.append(row)
    return pd.DataFrame(t1), pd.DataFrame(t2)


def in_season():
    t2b, t3 = [], []
    for s in TARGETS:
        s1, s2 = prev(s), prev(prev(s))
        full = pg[s]
        opener = datetime.date.fromisoformat(tg[s]["GAME_DATE"].min())
        debuts = bpv.debut_ids([s2, s1, s], {x: pg[x] for x in (s2, s1, s)}, draft)[s]
        last_n = {pid: len(g) for pid, g in by_player[s1].items()}
        shots = pg[s1].groupby("PLAYER_ID")[["FGM", "FG3M", "FGA"]].sum()
        shots = shots[shots["FGA"] >= ratings.SHOOTING_PRIOR_MIN_FGA]
        prior_efg = ((shots["FGM"] + 0.5 * shots["FG3M"]) / shots["FGA"]).to_dict()
        for days in DAYS:
            cut = (opener + datetime.timedelta(days=days)).isoformat()
            sofar, after = full[full["GAME_DATE"] < cut], full[full["GAME_DATE"] >= cut]
            league_efg = (sofar["FGM"].sum() + 0.5 * sofar["FG3M"].sum()) / max(sofar["FGA"].sum(), 1)
            rest = after.groupby("PLAYER_ID").agg(n=("FPTS", "size"), fpg=("FPTS", "mean"))
            for pid, g in sofar.groupby("PLAYER_ID"):
                n = len(g)
                if pid in debuts or last_n.get(pid, 0) >= 20 or pid not in rest.index or rest.loc[pid, "n"] < 5:
                    continue
                g = g.sort_values("GAME_DATE")
                raw, _ = ratings._production(g, "in-season", NO_OVERRIDES)
                g1, g2 = by_player[s1].get(pid), by_player[s2].get(pid)
                parts = [x for x in (g2, g1) if x is not None]
                pooled = pd.concat(parts) if parts else None

                def finish(prod):
                    if n >= ratings.RECALIBRATION_MIN_GAMES:
                        prod = ratings.RECALIBRATION[0] + ratings.RECALIBRATION[1] * prod
                        fga = g["FGA"].sum()
                        if fga > 0:
                            efg = (g["FGM"].sum() + 0.5 * g["FG3M"].sum()) / fga
                            prod += ratings.SHOOTING_REGRESSION * (efg - prior_efg.get(pid, league_efg)) * fga / n
                    return prod
                row = {"season": s, "days": days, "player": int(pid), "name": g["PLAYER_NAME"].iloc[-1], "n": n,
                       "actual": float(rest.loc[pid, "fpg"]), "w": int(rest.loc[pid, "n"]), "p0": finish(raw)}
                if pooled is not None and len(pooled) >= 20 and 1 <= last_n.get(pid, 0) and n <= 29:
                    prior = pooled["FPTS"].mean() + (age_adj(ages[s1], pid) if pooled["MIN"].mean() >= ratings.AGE_MIN_MPG else 0.0)
                    row["p1"] = finish(bpv.shrink(raw, n, prior, ratings.PRIOR_SEASON_K))
                    t3.append(row)
                elif (pooled is None or len(pooled) < 20) and n <= 19:
                    row["p1"] = finish(bpv.shrink(raw, n, draft_prior(s, pid), ratings.ROOKIE_K))
                    t2b.append(row)
        print(s, "in-season rows:", len(t2b), len(t3), flush=True)
    return pd.DataFrame(t2b), pd.DataFrame(t3)


def returners_espn():
    """T4: players back from a whole missed season, in the seasons with genuine preseason ESPN projections."""
    rows = []
    for s, year in {"2021-22": 2022, "2023-24": 2024, "2024-25": 2025, "2025-26": 2026}.items():
        s1, s2 = prev(s), prev(prev(s))
        proj = te.projections(year)
        proj["key"] = proj["name"].map(te.key)
        espn = proj.drop_duplicates("key").set_index("key")
        now = pg[s].groupby("PLAYER_ID").agg(n=("FPTS", "size"), fpg=("FPTS", "mean"))
        for pid, g2 in by_player[s2].items():
            if len(g2) < 20 or pid in by_player[s1] or pid not in now.index or now.loc[pid, "n"] < 10:
                continue
            base = g2["FPTS"].mean() + (age_adj(ages[s2], pid) if g2["MIN"].mean() >= ratings.AGE_MIN_MPG else 0.0)
            k = te.key(g2["PLAYER_NAME"].iloc[-1])
            e = float(espn.loc[k, "espn_fpg"]) if k in espn.index else np.nan
            rows.append({"season": s, "name": g2["PLAYER_NAME"].iloc[-1], "actual": round(float(now.loc[pid, "fpg"]), 1),
                         "games": int(now.loc[pid, "n"]), "without_espn": round(base, 1), "espn": round(e, 1),
                         "with_espn": round((1 - ratings.ESPN_FPG_WEIGHT) * base + ratings.ESPN_FPG_WEIGHT * e, 1) if e == e else None})
    return rows


def main():
    t1, t2a = between_seasons()
    t2b, t3 = in_season()
    out = {"rules": "docs/prereg-short-history.md",
           "T1_pooled_between_seasons": compare(t1, t1["p1"].to_numpy(), t1["p0"].to_numpy()),
           "T2a_draft_slot_between_seasons": compare(t2a, t2a["p1"].to_numpy(), t2a["p0"].to_numpy()),
           "T2b_draft_slot_in_season": compare(t2b, t2b["p1"].to_numpy(), t2b["p0"].to_numpy()),
           "T3_pooled_prior_in_season": compare(t3, t3["p1"].to_numpy(), t3["p0"].to_numpy())}
    p2 = t1.dropna(subset=["p2"])
    out["T1_info_p2_vs_p1"] = compare(p2, p2["p2"].to_numpy(), p2["p1"].to_numpy())
    out["T1_info_p2_vs_p0"] = compare(p2, p2["p2"].to_numpy(), p2["p0"].to_numpy())
    out["T4_returners_espn"] = returners_espn()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    for k, v in out.items():
        if isinstance(v, dict) and "mae_new" in v:
            print(k, {x: (round(v[x], 3) if isinstance(v[x], float) else v[x]) for x in
                      ["cases", "players", "mae_old", "mae_new", "mse_old", "mse_new", "ci", "seasons_better", "passes",
                       "mean_pred_old", "mean_pred_new", "mean_actual"]})
    print("T4:", json.dumps(out["T4_returners_espn"], indent=0))


if __name__ == "__main__":
    main()
