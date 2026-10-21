# Preregistration: fixing the single-game projections

Written 2026-10-21, after the first backtest failed (`docs/prereg-game-projections.md`, "Backtest result") and before
any of the changes below was tried. Code: `analysis/game_fix.py` (results in `analysis/game_fix.json`).

## Seasons

- **Design season: 2025-26.** Every choice below is made on it (and only it).
- **Test season: 2024-25**, used once, at the end, for the final version. Its "last season" is 2023-24.
  Game days from the 15th on, players who played (as in the first backtest).

## Candidate changes (the only ones tried)

Means:
- **M1, recent minutes:** expected minutes = w x his minutes averaged with a half-life of H games + (1 - w) x his
  average over the last 82; stats = his per-minute rates over the last 82 games x expected minutes, scaled to the
  fantasy-point anchor as before. Grid: H in {3, 5, 10}, w in {0, 0.5, 1}.
- **M2, opponent per stat:** 1 + c x (what the opponent allows of that stat per game, relative to the league, minus 1),
  c fitted per stat (least squares on the design season), opponents with 5+ games.
- **M3, back-to-back:** a multiplier on minutes for the second night of a back-to-back, fitted on the design season.
- **M4, home / away:** a multiplier per stat, fitted.
- **S, shrink:** mean = benchmark + s x (model mean - benchmark), s fitted per stat (s = 1 is no shrink).

Spread:
- **V, variance multiplier:** variance x k, k fitted per stat (maximum likelihood on the design season).

A change is kept for a stat only if it lowers that stat's Brier score on the design season's proxy lines (the first
backtest's measure); among the M1 grid, the best one. S and V are fitted last, on top of the kept changes.

## Final test (2024-25, once) and pass rules

The first backtest's checks and rules, unchanged: (1) accuracy vs the benchmark, (2) 10th-90th range coverage
75%-85% for every stat, (3) proxy-line buckets with 100+ bets within 5 points and Brier better than always 50%.

Added now, before seeing any result: check 2 counts whole numbers badly (a 0-1 block range includes every 0 and 1).
**Check 2b** measures the same thing properly: share of randomized PIT values (P(X < y) + u x P(X = y), u uniform) between
0.1 and 0.9, which is 80% for an honest forecast whatever the stat. **Pass 2b:** 75%-85% for every stat. Both are
reported; the verdict on ranges uses 2b.

## What passing would and wouldn't show

Passing says the probabilities are honest against a line set at the player's average. It doesn't show profit:
sportsbook lines are sharper than a player's average, and the break-even rate is 52.4% at -110 (about 58% per pick on
a 2-pick PrizePicks entry). That needs a test on real historical lines, which we don't have yet.

## Note on the run (2026-10-21)

The first run had a bug: two player-games with a projected mean of exactly 0 made the negative binomial's parameters
0/0, so the Brier score was NaN for every counting stat and no change could be chosen for them (only fantasy points
and points+rebounds+assists were really fitted). That run's test-season numbers were printed and seen. The bug is
mechanical (fixed by treating a zero mean as a point mass at 0) and the selection rules are unchanged, so the design
season was re-fitted and the test season re-run once more; both runs are reported.

## Result (added after running it, 2026-10-21)

`analysis/game_fix.json`. Chosen on 2025-26 (every stat kept M1 with a 3-game half-life and w = 0.5, and M2; some kept
M3, M4, S, V; details per stat in the file). Test season 2024-25 (23,572 player-games), fixed vs unfixed:

1. **Accuracy: passes.** Better than the benchmark for fantasy points (9.84 vs 10.05), points (4.63 vs 4.70),
   rebounds (1.92 vs 1.95) and assists (1.34 vs 1.36); the unfixed model tied the benchmark.
2. **Ranges (2b): passes.** 78.3%-82.4% inside for every stat (the old inclusive count still fails for the
   low-count stats, as expected).
3. **Proxy lines: fails the bucket rule for 8 of 9 stats** (passes for blocks). Brier is now better than always-50% for
   all 9 (it was worse for points, points+rebounds+assists and fantasy points before). The counting stats are still
   overconfident at the top (points: 70-75% predicted, 63% hit; points+rebounds+assists: 70-75%, 68%); fantasy points
   is underconfident (70-75% predicted, 77% hit).

Adopted for the live projections (it beats the unfixed model out of sample on every measure), with its probabilities
labelled as not yet calibrated. Profit is still untested: against a line set at the player's average the strongest
picks hit 60%-77%, but sportsbook lines already use recent minutes and matchups, which is where these gains come from.
