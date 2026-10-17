"""BPV vs published preseason rankings (analysts, consensus, ADP) and ESPN's projections.

Run:  python -m analysis.test_public_rankings      (writes analysis/test_public_rankings.json)

Lists: data/rankings/<source>_<season>.csv (rank,name; see data/rankings/SOURCES.md for the archived
snapshot each came from, all dated before opening night), plus
  BPV + ESPN blend (the app's preseason formula), BPV (age + crowding, no ESPN), ESPN projections.
Pool: everyone who played in the season or qualified the season before (rookies included, so lists that
rank rookies can take them; the BPV lists here have no rookie projection and rank rookies last, as in
analysis/draft_sim.py). Scored on actual season FPTS (ESPN default points).

Metrics, per season and averaged:
  top130   actual FPTS of the list's top 130 players (the players it would put on 10 teams x 13 spots)
  spearman rank correlation of the list's order with actual totals, over its top 150
  vs_field one team drafts by the list, the other nine by a common field (ESPN projections; and
           FantasyPros average ADP when available, i.e. the market), every seat run once; gain = that
           team's best-10 FPTS minus what a field-drafting team got from the same seat.
Caveats: most analyst lists and ADP target category leagues, not points, which handicaps them here.
The blend's constants were tuned on these seasons. Four seasons at most.
"""
import glob
import json
import math
import os
import re
import warnings

import numpy as np
import pandas as pd

from analysis import backtest as bt
from analysis import test_espn_projections as te_
from analysis import test_ten_team as tt
import bpv
import nba_data

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RANK_DIR = os.path.join(ROOT, "data", "rankings")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_public_rankings.json")
OWN = {"BPV + ESPN blend (app)": "BPV + ESPN hybrid (app)", "BPV (no ESPN)": "BPV + age + crowding",
       "ESPN projections": tt.ESPN}


def public_lists(season):
    out = {}
    for path in sorted(glob.glob(os.path.join(RANK_DIR, f"*_{season}.csv"))):
        slug = re.sub(rf"_{re.escape(season)}\.csv$", "", os.path.basename(path))
        df = pd.read_csv(path)
        out[slug] = df.sort_values("rank")["name"].tolist()
    return out


def to_ids(names_in_order, names):
    ids, missing, seen = [], [], set()
    for n in names_in_order:
        pid = names.get(te_.key(n))
        if pid is None:
            missing.append(n)
        elif pid not in seen:
            ids.append(pid)
            seen.add(pid)
    return ids, missing


def full_ranking(ids, pool):
    """The list's players first (those in the pool), then everyone else in a fixed order."""
    head = [p for p in ids if p in pool]
    rest = [p for p in sorted(pool) if p not in set(head)]
    return head + rest


def vs_field(rankings, field, actual):
    base = tt.run_draft([field] * tt.TEAMS, rankings)
    base10 = {s: tt.team_scores(base[s], actual)[1] for s in range(tt.TEAMS)}
    out = {}
    for c in rankings:
        gains = []
        for s in range(tt.TEAMS):
            order = [field] * tt.TEAMS
            order[s] = c
            gains.append(tt.team_scores(tt.run_draft(order, rankings)[s], actual)[1] - base10[s])
        out[c] = {"gain_best10": float(np.mean(gains)), "seats_better": int(sum(g > 0 for g in gains))}
    return out


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    res = {"seasons": {}}
    for t in te_.ESPN_SEASONS:
        pubs = public_lists(t)
        if not pubs:
            continue
        df = tt.season_frame(pg, tg, hist, league_p, league_q, t, names)
        h_t = hist[hist.season == t].set_index("PLAYER_ID")
        actual = df.actual_total.to_dict()
        for pid, v in h_t.fpts_total.items():          # rookies and others not in the preseason frame
            actual.setdefault(pid, float(v))
        pool = set(actual)
        rankings, info = {}, {}
        for label, col in OWN.items():
            rankings[label] = full_ranking(df[col][np.isfinite(df[col])].sort_values(ascending=False, kind="stable").index.tolist(), pool)
        for slug, order in pubs.items():
            ids, missing = to_ids(order, names)
            rankings[slug] = full_ranking(ids, pool)
            info[slug] = {"listed": len(order), "matched": len(ids), "unmatched_examples": missing[:8]}
        act = pd.Series(actual)
        block = {"lists": info, "top130": {}, "spearman_top150": {}}
        for c, r in rankings.items():
            block["top130"][c] = float(act.reindex(r[:130]).sum())
            top = r[:150]
            block["spearman_top150"][c] = float(pd.Series(-np.arange(len(top)), index=top).rank().corr(act.reindex(top).rank()))
        block["vs_espn_field"] = vs_field(rankings, "ESPN projections", actual)
        if "fp_adp_avg" in rankings:
            block["vs_adp_field"] = vs_field(rankings, "fp_adp_avg", actual)
        res["seasons"][t] = block
        print(t, json.dumps({k: block[k] for k in ("top130", "spearman_top150")}, indent=1), flush=True)

    labels = sorted({c for b in res["seasons"].values() for c in b["top130"]})
    summ = {}
    for c in labels:
        ss = [t for t, b in res["seasons"].items() if c in b["top130"]]
        summ[c] = {"seasons": len(ss)}
        for metric in ("top130", "spearman_top150"):
            summ[c][metric] = float(np.mean([res["seasons"][t][metric][c] for t in ss]))
        # Fair comparison: difference from the BPV blend in the same seasons only.
        summ[c]["top130_minus_blend"] = float(np.mean([res["seasons"][t]["top130"][c] - res["seasons"][t]["top130"]["BPV + ESPN blend (app)"] for t in ss]))
        summ[c]["vs_espn_gain_best10"] = float(np.mean([res["seasons"][t]["vs_espn_field"][c]["gain_best10"] for t in ss]))
        adp = [t for t in ss if "vs_adp_field" in res["seasons"][t]]
        if adp:
            summ[c]["vs_adp_gain_best10"] = float(np.mean([res["seasons"][t]["vs_adp_field"][c]["gain_best10"] for t in adp]))
            summ[c]["adp_seasons"] = len(adp)
    res["summary"] = summ
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
