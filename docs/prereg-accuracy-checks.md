# Preregistration: the "Our prediction / Result" checks on the Rankings page

Written 2026-10-21, after one night of games, before any of the new checks below was computed. Code:
`analysis/accuracy_tracker.py` (new: `availability`, `disagreements`), shown by `templates/index.html`. A
scoreboard: nothing in BPV changes because of it.

Each check states a prediction BPV made and what happened, with a pass rule fixed here. Every check is greyed out as
**too soon** until 14 days of games have been played after the snapshot (and its own minimum sample, below, is met).
Checks are shown for the final preseason snapshot and for the latest in-season (weekly) snapshot that has 14+ days
of games after it.

## Ranking checks (per snapshot)

| Check | Our prediction | Result | Pass |
|---|---|---|---|
| Order vs other rankings | BPV's order beats every other source | rank correlation per source (docs/prereg-ros-benchmarks.md) | BPV highest |
| Points per game | average miss, players with 10+ games since | the simple benchmark's miss | BPV's miss smaller |
| Likely range | 80% of players finish inside their range | share inside | 70% to 90% |
| Top 50 | BPV's top 50 average X FPTS/game | what they averaged | within 2.0 FPTS/game |
| Availability (new) | BPV's top 150 play X% of their team's games | share actually played | within 5 points |
| Head to head with ESPN | BPV's per-game miss is smaller | ESPN's miss, same players | BPV's smaller |
| Biggest disagreements with ESPN (new) | on the 20 players BPV and ESPN rank most differently, BPV is closer | how many BPV was closer on | more than 10 of 20 |

- **Availability:** predicted = the snapshot's `availability` averaged over BPV's top 150; actual = games played
  after the snapshot / his snapshot team's games after it, same players. Limit: health is better early in a season,
  so early numbers lean towards "played more than predicted".
- **Disagreements:** players in both snapshots and in either list's top 150, ranked within that set by each list and
  by actual total FPTS after the snapshot (0 if he didn't play). The 20 with the largest gap between BPV's and ESPN's
  rank; for each, the list whose rank is closer to his actual rank wins (a tie counts half).

## Nightly and weekly checks (from `analysis/live_checks.py`, unchanged)

| Check | Our prediction | Result | Pass |
|---|---|---|---|
| Injury report, per status | listed players play X% of the time | share who played | within 10 points, 20+ listings |
| This week's projections | beat season FPTS/game x games left | both average misses | better in most weeks, 3+ weeks |
| Preseason groups (rookies, returners, everyone else) | BPV's per-game miss beats ESPN's | ESPN's miss | BPV's smaller, 15+ players |

## Addendum (2026-10-21): which preseason ranking is graded

The preseason snapshot first saved (`bpv_2026-10-20_pre_2026-27.csv`, 8 AM on Oct 20) predates that evening's fix for
players returning from short seasons (commits aac2103 and ada6e3a). With only two people using the site, the checks
are for learning whether the current model works, so the graded snapshot was replaced by the opening-day version: the
fixed code (ada6e3a) run on the same 8 AM data (commit 39163c7, `data/live`), with no 2026-27 games. Checks on the
rebuild: the 8 AM code on the same data reproduces the published file exactly (650 players, identical values), and the
rebuilt per-game projections equal the frozen preseason prior (`data/preseason/prior_2026-27.csv`) for all 308 players
in it. The fix used no game results; one opening-night game had finished before it went live. The published file is
kept as `data/snapshots/archive/bpv_2026-10-20_pre_2026-27_as_published_8am.csv`.
