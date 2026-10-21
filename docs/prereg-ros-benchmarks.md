# Preregistration: BPV against every ranking we can collect without permission

Written 2026-10-21, before any of these comparisons had a result (one night of games played). Code:
`analysis/accuracy_tracker.py: benchmarks` (results in `data/accuracy.json`, shown on the Rankings page). A
scoreboard, not a model test: nothing in BPV changes because of it.

## Rankers

Each is a score known on the snapshot date; higher = better.

| Ranker | Score | Source |
|---|---|---|
| BPV | `bpv` in the BPV snapshot | `data/snapshots/bpv_*.csv` |
| ESPN projections | projected FPTS/game x projected games | `espn_*.csv`, same day and kind |
| ESPN crowd (in season) | % of ESPN leagues rostering him, ties broken by % starting | `crowd_*.csv`, same day and kind |
| ESPN crowd (preseason) | minus ESPN average draft position (undrafted, ESPN's placeholder 140: unscored) | `crowd_*_pre_*.csv` |
| Last season | last season's FPTS/game (players with 1+ game) | NBA game logs |
| Season so far (in season) | this season's FPTS/game before the snapshot date (1+ game) | NBA game logs |

ESPN's crowd numbers come from the same public API as its projections (`nba_data.espn_ownership`). A crowd file is
saved on each day a BPV snapshot is saved, so the two always share a date.

## Pool and outcome

- **Pool:** the union of each ranker's top 150 on that date (chosen before any outcome). A ranker that has no score
  for a pool player ranks him below everyone it scores.
- **Outcome:** actual total FPTS after the snapshot date (from opening night for preseason snapshots), 0 if he
  didn't play, so availability counts.

## Measures

1. **Primary:** rank correlation (Spearman) of each ranker's score with the outcome over the pool.
2. **Secondary:** top-130 hits, the share of a ranker's top 130 that finish in the pool's actual top 130 (130 = every
   roster spot in a 10-team, 13-player league).

Reported per BPV snapshot, and pooled as the average over snapshots, with how many snapshots BPV beat each ranker on.
A snapshot is labelled early (and greyed out on the site) until 14 days of games have been played after it.
The preseason summary uses only the final snapshot before opening night (`*_pre_*`); the older September snapshot
is scored but left out of the average (decided 2026-10-21 after one night of games, because only the final ranking
is the one people drafted with; it doesn't depend on that night's results).

## Known limits

- In-season snapshots are weekly, so nearby snapshots share most of their outcome: they aren't independent wins.
- ESPN's crowd is a ranking of who managers hold, not a projection; its top ~100 are near 100% rostered and tie,
  which costs it some correlation. That is a property of the signal, not a scoring choice.
- Whether ESPN's in-season projected games are rest-of-season or full-season hasn't been checked; it doesn't change
  its order much.
- The opening-week crowd files (`crowd_2026-10-20_*`) were captured on 2026-10-21, after opening night: a day more
  information than BPV had. That favours the crowd, so it can only make BPV look worse.
- The outcome is ESPN points-league FPTS, which BPV is built for. That is the question users ask, but ESPN's own
  projections are built for the same scoring, so the ESPN comparisons are the fairest.
