"""Simulate many drafts to compare ranking lists fairly (paper Section 14).

Each list gets two seats in a 10-team, 13-round snake draft; seats are shuffled
every draft; each team takes the best player left on its list. Teams are scored
by the actual FPTS their players produced in the target season.

Usage:
    python -m analysis.draft_sim --season 2025-26
    python -m analysis.draft_sim --season 2025-26 --ranking ESPN=espn.csv --ranking ADP=adp.csv

A ranking CSV needs a "name" column in draft order (best first). Players a list
doesn't include are only taken once everyone it does include is gone.
You can compare up to 5 lists (10 seats); the built-in lists (BPV + age, BPV, Models 3 and 5, last season total)
fill any open slots.
"""
import argparse
import csv
import math
import warnings

from analysis import backtest as bt
import bpv
import ratings

BUILT_IN = ["BPV + age", "BPV (replacement-level)", "M3 x career GP%", "M5 80/20 x career GP%",
            "Last season total FPTS"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--season", default="2025-26", help="season to score, e.g. 2025-26")
    parser.add_argument("--ranking", action="append", default=[], metavar="LABEL=FILE.csv")
    parser.add_argument("--sims", type=int, default=1000)
    parser.add_argument("--target", choices=["actual_total", "actual_managed"], default="actual_total")
    args = parser.parse_args()
    warnings.filterwarnings("ignore")

    pg, tg = bt.load()
    draft = bt.nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    df, _ = bt.preseason_frame(pg, hist, args.season, ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K,
                               league_p, league_q, age_curve=bt.age_curve_before(pg, args.season))

    # Add players who only appear in the target season (rookies), so lists that rank them can pick them.
    target = hist[hist["season"] == args.season].set_index("PLAYER_ID")
    for pid in target.index.difference(df.index):
        df.loc[pid, "actual_total"] = target.loc[pid, "fpts_total"]
        df.loc[pid, "actual_managed"] = target.loc[pid, "fpts_total"]
    names = hist.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    by_name = {ratings.normalize_name(n): pid for pid, n in names.items()}

    strategies = []
    for spec in args.ranking:
        label, path = spec.split("=", 1)
        with open(path, newline="", encoding="utf-8") as f:
            order = [row["name"] for row in csv.DictReader(f)]
        missing = [n for n in order if ratings.normalize_name(n) not in by_name]
        if missing:
            print(f"{label}: {len(missing)} names not matched (ignored): {', '.join(missing[:10])}")
        scores = {by_name[ratings.normalize_name(n)]: -i for i, n in enumerate(order)
                  if ratings.normalize_name(n) in by_name}
        df[label] = [scores.get(pid, -math.inf) for pid in df.index]
        strategies.append(label)
    for label in BUILT_IN:
        if len(strategies) >= 5:
            break
        df[label] = df[label].fillna(-math.inf)
        strategies.append(label)

    results = bt.simulate_drafts(df, strategies, n_sims=args.sims, target=args.target)
    print(f"{args.season}, {args.sims} simulated drafts, scored by {args.target}:")
    for label, r in sorted(results.items(), key=lambda kv: -kv[1]["mean"]):
        print(f"  {label:28s} {r['mean']:9,.0f}  (sd {r['sd']:,.0f})")


if __name__ == "__main__":
    main()
