"""ESPN's projected games in early-season availability (rules fixed beforehand in docs/prereg-early-availability.md).

Rebuilds the app's ratings at checkpoints after each opener and compares its availability (C0) with a blend that fades
ESPN's preseason projected games out as the team plays (C1). Writes analysis/early_availability.json.

    python -m analysis.early_availability
"""
import datetime
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ["NBA_OFFLINE"] = "1"

import nba_data   # noqa: E402  (NBA_OFFLINE must be set first)
import ratings   # noqa: E402
from analysis import test_espn_projections as te   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "early_availability.json")
SEASONS = {"2021-22": 2022, "2023-24": 2024, "2024-25": 2025, "2025-26": 2026}
DAYS = [1, 7, 14, 21, 28, 42]
KS = [5, 10, 20, 41, 82]
TOP, MIN_LEFT, STAR, BOOT = 250, 10, 40, 2000


def checkpoints(season):
    """Rebuild the app at each checkpoint; one row per player with the app's availability and what happened after."""
    pg_full, tg_full = nba_data.player_game_logs(season), nba_data.team_game_logs(season)
    opener = datetime.date.fromisoformat(tg_full["GAME_DATE"].min())
    reports = nba_data.injury_reports(season)
    proj = te.projections(SEASONS[season])
    proj["key"] = proj["name"].map(te.key)
    espn = proj.drop_duplicates("key").set_index("key")
    orig_p, orig_t, orig_r, orig_season = (nba_data.player_game_logs, nba_data.team_game_logs,
                                           nba_data.recent_injury_reports, os.environ.get("NBA_SEASON"))
    os.environ["NBA_SEASON"] = season
    rows = []
    try:
        for days in DAYS:
            today = opener + datetime.timedelta(days=days)
            cut = lambda f: (lambda s: (lambda df: df[df["GAME_DATE"] < today.isoformat()] if s == season else df)(f(s)))
            nba_data.player_game_logs, nba_data.team_game_logs = cut(orig_p), cut(orig_t)
            start = (today - datetime.timedelta(days=4)).isoformat()
            nba_data.recent_injury_reports = lambda *a, **k: reports[(reports["REPORT_DATE"] >= start)
                                                                    & (reports["REPORT_DATE"] < today.isoformat())].copy()
            ratings._season_started = lambda *a: True       # never write snapshots or priors from a rebuild
            df, meta = ratings.build(today=today)
            assert meta["mode"] == "in-season", (season, days, meta["mode"])
            played = tg_full[tg_full["GAME_DATE"] < today.isoformat()].groupby("TEAM_ABBREVIATION").size()
            left = tg_full[tg_full["GAME_DATE"] >= today.isoformat()].groupby("TEAM_ABBREVIATION").size()
            after = pg_full[pg_full["GAME_DATE"] >= today.isoformat()]
            for r in df[df["rank"] <= TOP].itertuples():
                k = te.key(r.name)
                if k not in espn.index or r.team not in left.index or left[r.team] < MIN_LEFT:
                    continue
                gp = float(espn.loc[k, "espn_gp"])
                if gp <= 0:
                    continue
                g_after = int(((after["PLAYER_ID"] == r.id) & (after["TEAM_ABBREVIATION"] == r.team)).sum())
                rows.append({"season": season, "days": days, "player": int(r.id), "name": r.name,
                             "c0": float(r.availability), "espn": min(1.0, ratings.ESPN_GAMES_SCALE * gp / ratings.SEASON_GAMES),
                             "team_played": int(played.get(r.team, 0)), "left": int(left[r.team]),
                             "out": r.report_status == "Out", "production": float(r.production),
                             "actual": min(1.0, g_after / left[r.team])})
            print(season, days, "days:", len(rows), "rows so far", flush=True)
    finally:
        nba_data.player_game_logs, nba_data.team_game_logs, nba_data.recent_injury_reports = orig_p, orig_t, orig_r
        if orig_season is None:
            os.environ.pop("NBA_SEASON", None)
        else:
            os.environ["NBA_SEASON"] = orig_season
    return rows


def blend(df, k):
    w = k / (k + df["team_played"])
    return np.where(df["out"], df["c0"], w * df["espn"] + (1 - w) * df["c0"])


def sq(pred, df):
    return float((df["left"] * (pred - df["actual"]) ** 2).sum() / df["left"].sum())


def main():
    df = pd.DataFrame([r for s in SEASONS for r in checkpoints(s)])
    # Leave one season out: k fitted on the other three seasons.
    c1 = np.empty(len(df))
    chosen = {}
    for s in SEASONS:
        train, test = df[df["season"] != s], (df["season"] == s).to_numpy()
        k = min(KS, key=lambda kk: sq(blend(train, kk), train))
        chosen[s] = k
        c1[test] = blend(df[test], k)
    c0 = df["c0"].to_numpy()
    a, w = df["actual"].to_numpy(), df["left"].to_numpy(float)
    e1, e0 = w * (c1 - a) ** 2, w * (c0 - a) ** 2
    players = df["player"].to_numpy()
    uniq = np.unique(players)
    idx = {p: np.flatnonzero(players == p) for p in uniq}
    rng = np.random.default_rng(7)
    diffs = []
    for _ in range(BOOT):
        t = np.concatenate([idx[p] for p in rng.choice(uniq, len(uniq))])
        diffs.append((e1[t].sum() - e0[t].sum()) / w[t].sum())
    by_season = {s: round(float((e1[m].sum() - e0[m].sum()) / w[m].sum()), 5)
                 for s in SEASONS for m in [(df["season"] == s).to_numpy()]}
    star = (df["production"] >= STAR).to_numpy()
    res = {
        "rows": int(len(df)), "players": int(len(uniq)), "k_chosen_loso": chosen,
        "sq_c0": float(e0.sum() / w.sum()), "sq_c1": float(e1.sum() / w.sum()),
        "diff": float((e1.sum() - e0.sum()) / w.sum()),
        "ci": [float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
        "by_season": by_season, "seasons_better": f"{sum(v < 0 for v in by_season.values())} of {len(by_season)}",
        "stars": {"rows": int(star.sum()), "diff": float((e1[star].sum() - e0[star].sum()) / w[star].sum())},
        "abs_c0": float((w * np.abs(c0 - a)).sum() / w.sum()), "abs_c1": float((w * np.abs(c1 - a)).sum() / w.sum()),
        "mean_c0": float((w * c0).sum() / w.sum()), "mean_c1": float((w * c1).sum() / w.sum()),
        "mean_actual": float((w * a).sum() / w.sum()),
        "by_checkpoint": {int(d): {"c0": round(sq(g["c0"].to_numpy(), g), 4),
                                   "c1": round(sq(c1[(df["days"] == d).to_numpy()], g), 4)}
                          for d, g in df.groupby("days")},
        "k_fitted_all_seasons": min(KS, key=lambda kk: sq(blend(df, kk), df)),
    }
    res["passes"] = bool(res["ci"][1] < 0 and sum(v < 0 for v in by_season.values()) >= 3 and res["stars"]["diff"] <= 0)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"rules": "docs/prereg-early-availability.md", **res}, f, indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
