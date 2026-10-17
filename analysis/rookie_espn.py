"""Incoming-rookie projections: blend ESPN in? Season totals (docs/prereg-rookie-espn.md).

Run:  python -m analysis.rookie_espn       (writes analysis/rookie_espn.json)

Pool: players drafted the summer before each ESPN season whom ESPN projected; never-played rookies count as 0.
  A current app: draft-range baseline FPTS/game (app's 5-season window) x league availability x 82.
  B app's veteran rule: 62.5% A + 37.5% ESPN per game; games = min(82, 0.86 x ESPN games).
  C ESPN alone: ESPN FPTS/game x ESPN games.
Names are matched through the draft list too, so rookies who never played stay in the pool.
"""
import json
import os
import warnings

import numpy as np
import pandas as pd

from analysis import round10 as r10
from analysis import test_espn_projections as te_
import bpv
import nba_data
import ratings

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rookie_espn.json")


def season_rows(t, year, draft):
    """One row per drafted rookie ESPN projected for season t, with the three projections and the actual total."""
    start = nba_data.season_start_year(t)
    window = [nba_data.season_string(y) for y in range(start - ratings.HISTORY_SEASONS, start)]   # as the app saw it
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in window + [t]}
    tg = {s: nba_data.team_game_logs(s) for s in window}
    hist = bpv.availability_history(window, {s: pg[s] for s in window}, tg, draft)
    league_p, _ = bpv.league_availability(hist)
    baselines = bpv.rookie_baselines(bpv.rookie_seasons(window, {s: pg[s] for s in window}, draft, hist))

    drafted = draft[draft.SEASON.astype(int) == start].drop_duplicates("PERSON_ID")
    names = te_.name_map(pg)
    names.update({te_.key(n): pid for pid, n in zip(drafted.PERSON_ID, drafted.PLAYER_NAME)})   # never-played rookies
    espn = r10.espn_full(year, names)

    actual = pg[t].groupby("PLAYER_ID").FPTS.agg(["sum", "size", "mean"])
    rows = []
    for d in drafted.itertuples():
        if d.PERSON_ID not in espn.index:
            continue
        e = espn.loc[d.PERSON_ID]
        bucket = bpv.pick_bucket(d.OVERALL_PICK)
        base = baselines.get(bucket, baselines["undrafted"])["fpts_per_game"]
        espn_games = min(ratings.SEASON_GAMES, ratings.ESPN_GAMES_SCALE * e.espn_gp)
        a = actual.loc[d.PERSON_ID] if d.PERSON_ID in actual.index else None
        rows.append({
            "PLAYER_ID": int(d.PERSON_ID), "name": d.PLAYER_NAME, "season": t, "pick": d.OVERALL_PICK, "bucket": bucket,
            "pA": base * league_p * ratings.SEASON_GAMES,
            "pB": ((1 - ratings.ESPN_FPG_WEIGHT) * base + ratings.ESPN_FPG_WEIGHT * e.espn_fpg) * espn_games,
            "pC": e.espn_fpg * e.espn_gp,
            "fpgA": base, "fpgB": (1 - ratings.ESPN_FPG_WEIGHT) * base + ratings.ESPN_FPG_WEIGHT * e.espn_fpg, "fpgC": e.espn_fpg,
            "actual": float(a["sum"]) if a is not None else 0.0, "games": int(a["size"]) if a is not None else 0,
            "actual_fpg": float(a["mean"]) if a is not None else np.nan,
        })
    return pd.DataFrame(rows), {"drafted": len(drafted), "espn_projected": len(rows), "league_p": league_p}


def main():
    draft = nba_data.draft_history()
    frames, pools = [], {}
    for t, year in te_.ESPN_SEASONS.items():
        f, info = season_rows(t, year, draft)
        frames.append(f)
        pools[t] = info
    d = pd.concat(frames).set_index("PLAYER_ID")
    d["in_pool"] = True
    d["top"] = d.groupby("season").actual.transform(lambda x: x >= x.quantile(0.9))

    res = {"pool": pools, "rookies": int(len(d)), "never_played": int((d.games == 0).sum())}
    results = {}
    for k in ["pB", "pC"]:
        r = r10.paired(d, k, "pA", "actual")
        r["top50_diff"] = r10.paired(d, k, "pA", "actual", mask=d.top)["mean_diff"]
        results[k] = r
    v = r10.verdicts(results, ["pB", "pC"])
    for k, r in results.items():
        res[k] = {**r10.strip(r), "top10pct_diff": r["top50_diff"], "verdict": v[k]}
        res[k].pop("top50_diff", None)

    # Reported only: rank correlation within the pool, per-game error for 20+ games, error by draft range.
    res["spearman"] = {t: {k: float(g[k].corr(g.actual, method="spearman")) for k in ["pA", "pB", "pC"]}
                       for t, g in d.groupby("season")}
    played = d[d.games >= 20].copy()
    played["in_pool"] = True
    res["per_game_20plus"] = {k: r10.strip(r10.paired(played, k, "fpgA", "actual_fpg")) for k in ["fpgB", "fpgC"]}
    res["mae_by_bucket"] = {b: {k: float((g[k] - g.actual).abs().mean()) for k in ["pA", "pB", "pC"]} | {"n": int(len(g))}
                            for b, g in d.groupby("bucket")}
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
