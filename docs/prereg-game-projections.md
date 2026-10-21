# Preregistration: single-game stat projections

Written 2026-10-21, before any projection was made or scored. Code: `game_projections.py` (the model),
`analysis/live_checks.py` (logging and scoring, results in `data/tracking/summary.json`), `analysis/game_backtest.py`
(the 2025-26 backtest). The projections are new; BPV itself doesn't change because of them.

## Model (fixed now)

For each player whose team plays on the game day, with 5+ games in his last 82 (this season, then last season):

- **Mean, if he plays:** his stat mix over those last 82 games (points, rebounds, assists, threes, steals, blocks,
  turnovers, field goals and free throws), scaled so that its ESPN fantasy points equal BPV's per-game projection
  (`production`), times the opponent factor already used for weekly projections: 1 + 0.69 x (fantasy points the
  opponent allows per game relative to the league, minus 1), used once the opponent has played 5+ games. The scale is
  capped to 0.5-1.6.
- **Spread:** his game-to-game variance of each stat over the same games (scaled by the same factor squared), shrunk
  toward a league curve with 20 pseudo-games. The league curve is log(variance) = a + b x log(mean), fitted per stat on
  last season's players with 20+ games.
- **Shape:** counting stats (points, rebounds, assists, threes, steals, blocks, turnovers, points+rebounds+assists) are
  negative binomial with that mean and variance (Poisson if the variance isn't above the mean); ESPN fantasy points are
  normal.
- **Chance he plays:** the injury report's calibrated rates (`bpv.PLAY_PROBABILITY`) when he's listed; otherwise 0.97,
  or 0.80 if his team has played since his last game.

Projections are **conditional on playing**, as props are (a bet on a player who doesn't play is void).

## What is logged

The morning refresh (before noon, no game that day yet) logs every player projected for 10+ minutes that day: means, variances,
shapes, the 10th/50th/90th percentiles, the chance he plays, his injury status, and a **simple benchmark**: his average
this season before that day (last season's if he has under 3 games this season). Also a **proxy line** per stat: the
benchmark rounded down plus 0.5 (a stand-in for a sportsbook line until real lines are collected), and the model's
chance of going over it.

## Checks and pass rules

Scored on players who played (1+ minute). Judged once 14 game days and 1,000 player-games are logged.

1. **Accuracy:** average miss (absolute error) of the mean vs the benchmark, for fantasy points, points, rebounds and
   assists. **Pass:** smaller for fantasy points and for at least 2 of points, rebounds and assists.
2. **Ranges:** share of outcomes inside the 10th-90th percentile range, per stat. **Pass:** 75%-85% for every stat.
3. **Proxy lines:** predicted chance of the over, in 5-point buckets (50-55% ... 90%+), vs how often the over hit.
   **Pass:** every bucket with 100+ bets within 5 points, and a Brier score better than always saying 50%.
4. **Chance he plays:** for players not on the injury report, predicted vs actual share who played, per group (0.97
   and 0.80). Reported; no pass rule (the listed players are already checked by the injury-report cards).

## Backtest (before the live record exists)

`analysis/game_backtest.py` replays 2025-26: for every game day from the 15th on, the model is run with only the games
before that day, with one change: BPV's production isn't recomputed for every date, so the mean's fantasy-point anchor
is the player's season-to-date average shrunk toward last season (8 pseudo-games), as BPV does in season. Checks 1-3
are scored on it with the same rules. It tests the spreads and shapes, which are the new part; the live record tests
the whole thing.

## Known limits

- The proxy line isn't a real line: books set theirs with information we don't have (late news, matchups, minutes).
  Passing check 3 says the probabilities are honest, not that they beat a book.
- Teammates being out isn't modelled: a player's mean doesn't rise when a teammate sits.
- No rest, back-to-back or home/away effects.

## Backtest result (added after running it, 2026-10-21)

`analysis/game_backtest.json`: 23,923 player-games over 150 game days of 2025-26. **It fails all three checks.**

1. **Accuracy: fails.** The model's average miss equals the simple benchmark's (his season average so far): points
   4.71 vs 4.68, rebounds 1.92 vs 1.92, assists 1.37 vs 1.36, fantasy points 10.00 vs 10.01. For one game it adds
   nothing over his average.
2. **Ranges: fails.** Points, points+rebounds+assists and fantasy points are right (80.3%, 80.0%, 79.9% inside the
   10th-90th range). Rebounds, assists, threes, steals, blocks and turnovers cover 87%-94%; much of that is how the
   check counts whole numbers (a range of 0-1 blocks includes every 0 and 1), so this check suits low-count stats badly.
3. **Proxy lines: fails.** The probabilities are overconfident: when the model gave points over/under 60-65%, it hit
   52%; 65-70%, 56%; 70-75%, 58%. Brier score worse than always saying 50% for points (0.2565 vs 0.2500), points+
   rebounds+assists and fantasy points. The model's lean (above or below his average) is right a bit more often than
   not, but far less often than it says.

What that means: the averages and the point / fantasy-point ranges are usable as information; the over/under
probabilities are not, and nothing here suggests an edge over sportsbook lines (which are better than a player's
average). Caveat: the backtest anchor is a shrunk season average, not BPV; the live log (from 2026-10-22) tests the
BPV-anchored version under the same rules.
