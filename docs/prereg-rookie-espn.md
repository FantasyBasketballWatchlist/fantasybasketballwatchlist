# Incoming-rookie projections: ESPN blend, season totals (pre-registration)

Written 2026-10-17, before the test below was run.

## Why

Players with no NBA games get the average rookie season for their draft range (`bpv.rookie_baselines`) and
league-average availability. Every other player is blended 37.5% with ESPN's preseason projection, but incoming
rookies are not. Round 10 item 6C (`analysis/round10_rookies.py`) tested 75% ESPN + 25% a draft-slot prior on
**FPTS per game for rookies with 20+ games**: −0.33 (−1.54 to +0.86), 3 of 4 seasons, 86 rookies, not adopted.
That pool drops the rookies who barely played (outcome-selected), and drafts are decided on **season totals**,
which it didn't score. This test asks that question instead.

## Design

- **Seasons**: the four ESPN seasons (`test_espn_projections.ESPN_SEASONS`: 2021-22, 2023-24, 2024-25, 2025-26).
  None are in the frozen holdout (2014-15..2018-19).
- **Pool** (fixed before the season, not outcome-selected): players drafted that summer whom ESPN gave a
  preseason projection (games > 0). Players who never play count with 0 FPTS.
- **Target**: actual regular-season total FPTS.
- **Arms** (only past data for each season, as the app would have had it; no new fitted constants):
  - **A, current app**: draft-range baseline FPTS/game from the app's 5-season window, times league availability
    `league_p` × 82 games.
  - **B, app's veteran rule**: per game 62.5% A + 37.5% ESPN; games = min(82, 0.86 × ESPN games)
    (`ratings.ESPN_FPG_WEIGHT`, `ESPN_GAMES_SCALE`, unchanged).
  - **C, ESPN alone**: ESPN FPTS/game × ESPN games.
  The app's +0.31 per preseason minute adjustment is left out of every arm (no preseason data before 2022-23).
- **Primary metric**: absolute error of season-total FPTS, paired per player (variant − A), player-clustered
  bootstrap (`round10.paired`).
- **Adoption rule** (same as Round 10): a variant is adopted only if it (a) beats A in at least 3 of 4 seasons,
  (b) has a paired interval entirely below zero after a Holm correction over B and C, and (c) is not worse than
  A for the actual top 10% of the pool by total FPTS.
- **Reported, not used for adoption**: Spearman rank correlation with actual totals within the pool per season;
  per-game error for rookies with 20+ games; results by draft range.
- If both pass, the app uses the one with the lower mean error. If neither passes, nothing changes.
