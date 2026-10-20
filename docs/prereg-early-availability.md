# Preregistration: ESPN's projected games in early-season availability

Written 2026-10-20, before any result was computed. Script: `analysis/early_availability.py` (results in
`analysis/early_availability.json`).

## The problem

Before a season, a veteran's availability is ESPN's projected games x 0.86 / 82 (tested: it knows about injuries,
suspensions and holdouts that a player's history doesn't). The moment the season's first box score appears, every
player switches to BPV's history-based availability, so that information is thrown away for players who haven't played
yet. On opening night 2026-27, Mark Williams went from 25% to 69% availability (#192 to #112) without playing.

## Test

- Seasons with genuine pre-opener ESPN projections: 2021-22, 2023-24, 2024-25, 2025-26 (as in `analysis/test_espn_totals.py`).
- Checkpoints: 1, 7, 14, 21, 28 and 42 days after each opener. At each, the app's own ratings are rebuilt
  (`ratings.build`, game logs cut at the date, that week's official injury reports): that availability is **C0**.
- Players: ESPN projected them, ranked in the app's top 250 at the checkpoint, team has 10+ games left.
- Target: share of his team's remaining games he played.
- **C1:** availability = w x ESPN + (1 - w) x C0, with ESPN = min(1, 0.86 x projected games / 82) and
  w = k / (k + games his team has played), so ESPN's view fades as the season goes on. Players listed Out on the
  injury report keep C0 (that rule was tested on its own). k is chosen from {5, 10, 20, 41, 82} leave-one-season-out,
  by squared error on the other three seasons.
- Error: **squared error** of the share (availability feeds an expected value), weighted by games left. Absolute
  error reported alongside.

## Adoption rule (fixed now)

C1 is added if, out of sample: its squared error is lower pooled, with a 95% interval (bootstrap clustered by player)
that excludes zero; it is better in at least 3 of the 4 seasons; and it is not worse for stars (preseason production
40+ FPTS per game). Otherwise nothing changes.

## Known limits

- Rosters for past seasons come from the current roster file (only today's is saved), which affects which players
  with no games yet are listed; the comparison is between C0 and C1 on the same players, so both see the same lists.
- All four seasons were used to fit the ESPN blend itself; this question (fading it in season) wasn't.
- Four seasons is few; one season moving the other way can fail the rule.
