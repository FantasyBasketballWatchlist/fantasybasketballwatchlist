"""Where does the experts' preseason edge come from? (rules fixed beforehand in docs/prereg-ecr-gap.md)

Splits ECR's advantage in ordering players (pairwise, against actual season totals) into groups known before the
season: rookies, injury/short season, team changers, second-year players, settled veterans. Writes
analysis/ecr_gap.json.

    python -m analysis.ecr_gap
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

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ecr_gap.json")
GROUPS = ["no NBA history", "injury / short season", "team changer", "second year", "settled veteran"]


def contributions(d):
    """Per-player share of ECR's extra correctly ordered pairs (ECR minus the blend), over all pairs in the pool."""
    act = d["act_total"].to_numpy(float)
    base = d["base_total"].to_numpy(float)
    ecr = -d["ecr"].fillna(300).to_numpy(float)           # lower rank = better
    da = np.sign(act[:, None] - act[None, :])
    valid = da != 0
    ok = lambda s: np.where(np.sign(s[:, None] - s[None, :]) == 0, 0.5, (np.sign(s[:, None] - s[None, :]) == da).astype(float))
    diff = np.where(valid, ok(ecr) - ok(base), 0.0)
    np.fill_diagonal(diff, 0)
    pairs = valid.sum() / 2
    return diff.sum(axis=1) / 2, pairs, (np.where(valid, ok(base), 0).sum() / 2) / pairs, (np.where(valid, ok(ecr), 0).sum() / 2) / pairs


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    debuts = bpv.debut_ids(bt.SEASONS, pg, draft)
    player_name = pd.concat([g[["PLAYER_ID", "PLAYER_NAME"]] for g in pg.values()]).drop_duplicates("PLAYER_ID", keep="last")         .set_index("PLAYER_ID")["PLAYER_NAME"].to_dict()
    rows, summary = [], {}
    for t in r10.SEASONS:
        d = r10.season_data(pg, tg, hist, league_p, league_q, t, names, debuts)
        prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
        played_prev = hist[hist.season == prev].set_index("PLAYER_ID").played
        top = lambda s: set(s.sort_values(ascending=False).head(150).index)
        pool = top(d.base_total) | top(d.espn_total.dropna()) | set(d.ecr[d.ecr <= 150].index)
        d = d[d.index.isin(pool)].copy()
        d["played_prev"] = played_prev.reindex(d.index).fillna(0)
        seen_before = set(hist[hist.season.map(bt.SEASONS.index) < bt.SEASONS.index(t)].PLAYER_ID)
        d["group"] = np.select(
            [~d.index.isin(seen_before),
             (d.played_prev < 20) | (d.espn_gp < 60),
             d.team_changer,
             d.second_year],
            GROUPS[:4], default=GROUPS[4])
        contrib, pairs, c_base, c_ecr = contributions(d)
        d["contrib"] = contrib
        d["base_rank"] = d.base_total.rank(ascending=False)
        d["act_rank"] = d.act_total.rank(ascending=False)
        summary[t] = {"pool": int(len(d)), "pairs": int(pairs), "concordance_blend": round(c_base, 4),
                      "concordance_ecr": round(c_ecr, 4), "ecr_extra_correct_pairs": round(float(contrib.sum()), 1)}
        # Top-50 pairs only: both players in either list's top 50.
        top50 = d[(d.base_rank <= 50) | (d.ecr <= 50)]
        c50, p50, b50, e50 = contributions(top50)
        summary[t]["top50_pairs"] = {"pairs": int(p50), "concordance_blend": round(b50, 4), "concordance_ecr": round(e50, 4)}
        d["season"] = t
        d["name"] = [player_name.get(i, str(i)) for i in d.index]
        rows.append(d.reset_index().rename(columns={"index": "PLAYER_ID"}))
    all_ = pd.concat(rows, ignore_index=True)
    total = all_.contrib.sum()
    by_group = {}
    for g in GROUPS:
        x = all_[all_.group == g]
        per_season = x.groupby("season").contrib.sum()
        by_group[g] = {"players": int(len(x)), "contribution": round(float(x.contrib.sum()), 1),
                       "share_of_ecr_edge": round(float(x.contrib.sum() / total), 3) if total else None,
                       "per_player": round(float(x.contrib.mean()), 2),
                       "by_season": {s: round(float(v), 1) for s, v in per_season.items()},
                       "seasons_ecr_ahead": f"{int((per_season > 0).sum())} of {len(per_season)}"}
    ages = {}
    for label, m in [("age 32+", all_.age >= 32), ("age <= 23", all_.age <= 23)]:
        ages[label] = {"players": int(m.sum()), "contribution": round(float(all_[m].contrib.sum()), 1),
                       "per_player": round(float(all_[m].contrib.mean()), 2)}
    # Biggest single contributors either way, with what the blend got wrong.
    all_["blend_games_err"] = all_.base_gp - all_.act_games
    all_["blend_fpg_err"] = all_.base_fpg - all_.act_fpg
    cols = ["season", "name", "group", "contrib", "ecr", "base_rank", "act_rank", "base_fpg", "act_fpg", "base_gp", "act_games"]
    show = lambda x: x[cols].round(1).to_dict(orient="records")
    out = {"rules": "docs/prereg-ecr-gap.md", "seasons": summary, "total_ecr_extra_correct_pairs": round(float(total), 1),
           "by_group": by_group, "overlapping": ages,
           "top_ecr_gains": show(all_.nlargest(15, "contrib")), "top_blend_gains": show(all_.nsmallest(10, "contrib"))}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, default=float)
    print(json.dumps({k: v for k, v in out.items() if not k.startswith("top_")}, indent=1))
    for k in ("top_ecr_gains", "top_blend_gains"):
        print(k)
        for r in out[k]:
            print("  ", r)


if __name__ == "__main__":
    main()
