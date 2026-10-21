# Preregistration: BPV and NBA team win totals

Written 2026-10-21, before any projection was compared with a line or a result. Code: `analysis/win_totals.py`
(results in `analysis/win_totals.json`). Lines: `data/win_totals/preseason_lines.csv` (sources per season in the file).

## The idea

A team's wins come mostly from how good its players are and how many games they play: BPV's per-game value and
availability, which beat the expert consensus for rest-of-season player value. Season-long markets are thought to be
softer than nightly props.

## Data

- Seasons **2020-21** (72 games) to **2025-26**, preseason over/under win totals for all 30 teams (180 lines). Lines
  are assumed priced at -110 (the archives don't give prices): break-even 52.4%.
- Actual wins: team game logs.

## Team strength (only what was known before the season)

- Each player's preseason BPV as the app computed it for past seasons (`analysis/backtest.preseason_frame`: per-game
  value with age, availability p_hat, replacement level R), for players with 20+ games the season before.
- Value above replacement over the season: max(0, per-game value - R) x p_hat x the season's games.
- Team: his last team the season before, unless he played for a different team in the season's first 21 days (offseason
  moves). Rookies and players with under 20 games last season aren't counted (a known gap).
- **S** = the sum over a team's players, standardized within the season (mean 0, SD 1).

## Projection

wins per game = a + b x S + c x (last season's win share - 0.5), fitted by least squares on the **design seasons
2020-21, 2021-22, 2022-23**; projected wins = that x the season's games.

## Bet

Over if projected wins - line >= 2.0, under if <= -2.0, else no bet. $1 at -110 each; a whole-number result equal to
the line (none here: all lines are .5) would push.

## Test (once): 2023-24, 2024-25, 2025-26 (90 lines)

- **Pass:** bets win at least 55% overall **and** above 52.4% in at least 2 of the 3 seasons.
- Reported: number of bets and ROI; mean absolute error of the projection vs the line's own (lines are good forecasts:
  matching them would already be notable); a blend line + w x (projection - line) with w fitted on the design seasons;
  the same rule with a 3.0-win threshold.

## Known limits

- At most ~90 test lines, and probably 40-60 bets: only a large edge can pass; a real small edge may not.
- Lines for 2020-21 to 2022-23 aren't strictly openers (dated tables), and 2023-24's come from a different site.
- Fantasy points aren't wins (defense, efficiency, coaching aren't in BPV); last season's record partly covers them.
