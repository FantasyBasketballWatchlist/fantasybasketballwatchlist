"""Round 10, item 6 (docs/prereg-round10.md): rookie prior from draft slot and age.

Run:  python -m analysis.round10_rookies       (writes analysis/round10_rookies.json)

Rookies = first NBA season in 2010-11..2025-26 (drafted that summer, or not seen in any earlier loaded
season); scored on FPTS per game for those with 20+ games, leave-one-season-out.
  6A current app baseline: average rookie FPTS/game for the draft range (bpv.PICK_BUCKETS).
  6B OLS on log(pick) and age (undrafted rookies keep the 6A value).
  6C 25% 6B + 75% ESPN's per-game projection (ESPN seasons only, rookies ESPN projected).
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

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "round10_rookies.json")
ALL = [nba_data.season_string(y) for y in range(2009, 2026)]


def main():
    pg = {s: bpv.add_fpts(nba_data.player_game_logs(s)) for s in ALL}
    draft = nba_data.draft_history()
    picks = draft.drop_duplicates("PERSON_ID").set_index("PERSON_ID").OVERALL_PICK
    debuts = bpv.debut_ids(ALL, pg, draft)
    rows = []
    for s in ALL[1:]:
        g = pg[s][pg[s].PLAYER_ID.isin(debuts[s])].groupby("PLAYER_ID").agg(fpg=("FPTS", "mean"), gp=("FPTS", "size"))
        ages = nba_data.player_ages(s).set_index("PLAYER_ID").AGE
        g["age"] = ages.reindex(g.index)
        g["pick"] = picks.reindex(g.index)
        g["season"] = s
        rows.append(g)
    r = pd.concat(rows).reset_index().rename(columns={"index": "PLAYER_ID"})
    r = r[(r.gp >= 20) & r.age.notna()]
    r["bucket"] = r.pick.map(bpv.pick_bucket)
    r["lp"] = np.log(r.pick)

    # ESPN projections for rookies in the ESPN seasons.
    names = te_.name_map({s: pg[s] for s in ALL[-7:]})
    espn = []
    for t, year in te_.ESPN_SEASONS.items():
        e = r10.espn_full(year, names)
        e["season"] = t
        espn.append(e.reset_index()[["PLAYER_ID", "season", "espn_fpg"]])
    r = r.merge(pd.concat(espn), on=["PLAYER_ID", "season"], how="left")

    r["p6A"], r["p6B"] = np.nan, np.nan
    for s in r.season.unique():
        tr, te = r[r.season != s], r.season == s
        means = tr.groupby("bucket").fpg.mean()
        r.loc[te, "p6A"] = r.loc[te, "bucket"].map(means)
        d = tr[tr.pick.notna()]
        X = np.column_stack([np.ones(len(d)), d.lp, d.age])
        coef, *_ = np.linalg.lstsq(X, d.fpg.to_numpy(), rcond=None)
        m = te & r.pick.notna()
        r.loc[m, "p6B"] = coef[0] + coef[1] * r.loc[m, "lp"] + coef[2] * r.loc[m, "age"]
    r["p6B"] = r.p6B.fillna(r.p6A)
    r["p6C"] = np.where(r.espn_fpg.notna(), 0.25 * r.p6B + 0.75 * r.espn_fpg, np.nan)

    r = r.set_index("PLAYER_ID")
    r["in_pool"] = True
    r["act_top50"] = r.fpg >= r.fpg.quantile(0.9)          # best 10% of rookies stand in for "top 50"
    res = {"rookies": int(len(r)), "seasons": sorted(r.season.unique().tolist())}
    b = r10.paired(r, "p6B", "p6A", "fpg")
    b["top50_diff"] = r10.paired(r, "p6B", "p6A", "fpg", mask=r.act_top50)["mean_diff"]
    b["wins_note"] = f"wins counted over {r.season.nunique()} seasons"
    res["6B"] = r10.strip(b)
    res["6B"]["verdict"] = r10.verdicts({"6B": b}, ["6B"])["6B"]
    e = r[r.p6C.notna()]
    c = r10.paired(e, "p6C", "p6A", "fpg")
    c["top50_diff"] = r10.paired(e, "p6C", "p6A", "fpg", mask=e.act_top50)["mean_diff"]
    res["6C"] = r10.strip(c)
    res["6C"]["verdict"] = r10.verdicts({"6C": c}, ["6C"])["6C"]
    res["espn_alone_vs_6A"] = r10.strip(r10.paired(e, "espn_fpg", "p6A", "fpg"))
    with open(OUT, "w") as fh:
        json.dump(res, fh, indent=2, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    main()
