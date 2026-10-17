"""Save today's BPV rankings as a dated file, so they can be scored after the season.

Run before the season starts (and at any checkpoint you want to evaluate later):
    python -m analysis.snapshot

Writes data/snapshots/bpv_<date>.csv, ranked best first, with a "name" column so the
file can be passed straight to analysis/draft_sim.py as a ranking. Save competitors'
rankings the same day as CSVs with a "name" column (e.g. data/snapshots/espn_<date>.csv).
When the season is over, set BACKTEST_LAST_SEASON to it and run, for example:
    python -m analysis.draft_sim --season 2026-27 --ranking BPV=data/snapshots/bpv_2026-10-15.csv --ranking ESPN=...
Snapshot files are meant to be committed to git, so the commit date proves when they were made.
"""
import datetime
import os
import warnings

import ratings

OUT_DIR = ratings.SNAPSHOT_DIR


def main():
    warnings.filterwarnings("ignore")
    players, meta = ratings.build()
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"bpv_{datetime.date.today().isoformat()}.csv")
    players.assign(target_season=meta["target_season"])[ratings.SNAPSHOT_COLUMNS].to_csv(path, index=False)
    print(f"{path}: {len(players)} players; mode {meta['mode']}, based on {meta['season']}, "
          f"replacement level {meta['replacement_level']:.1f}")


if __name__ == "__main__":
    main()
