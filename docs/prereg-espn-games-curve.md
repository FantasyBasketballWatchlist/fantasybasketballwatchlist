# Preregistration: turning ESPN's projected games into availability

Written 2026-10-20, before any result was computed. Script: `analysis/espn_games_curve.py` (results in
`analysis/espn_games_curve.json`).

## The problem

Before a season, availability is ESPN's projected games x 0.86 / 82 (capped at 1). ESPN's low projections carry injury
news, but the straight line under-uses it: regulars ESPN projected for 21-40 games played 3.5 on average, and 41-60
projected played 36. The expert-gap decomposition found injury news is the largest single source of the experts'
preseason edge.

## Test

- Seasons with genuine preseason ESPN projections: 2021-22, 2023-24, 2024-25, 2025-26.
- Players: veterans BPV applies ESPN's games to (20+ games and 15+ minutes per game last season) with an ESPN projection,
  or flagged out by ESPN (0 projected games, or no projection while listed OUT; treated as 0 games).
- Target: games played that season / 82.
- **C0 (now):** min(1, 0.86 x games / 82); flagged out: 14 / 82.
- **C1:** a non-decreasing curve from ESPN's projected games to the share played (isotonic regression, players
  weighted equally, flagged-out players at 0 games), fitted leave-one-season-out on the other three seasons, read off
  by linear interpolation between fitted points.
- Error: squared error of the share (availability feeds an expected value); absolute error reported too.
  Secondary: season-total FPTS error with BPV's preseason production (the blend), C0 vs C1 availability.

## Adoption rule (fixed now)

C1 replaces C0 if, out of sample, its squared error is lower pooled with a 95% interval (bootstrap clustered by player)
that excludes zero, it is better in at least 3 of the 4 seasons, it is not worse for stars (40+ FPTS per game last
season), and the season-total error is not worse pooled.

## Known limits

- 0.86 was itself fitted on these four seasons, so C0 has an in-sample advantage; C1 is fitted out of sample.
- Few players sit at the low end of the curve (it is fitted mostly on healthy players); that is where the news is, so
  the low end is the least certain part.

## Result (added after running it, 2026-10-20)

`analysis/espn_games_curve.json`, 1,169 veteran player-seasons. **C1 fails:** squared error 0.0589 -> 0.0591 (interval
-0.0019 to +0.0024), 2 of 4 seasons, stars worse (+0.0085), season-total error worse (506 -> 511). Below about 55
projected games ESPN's number stops discriminating (everyone there played ~28-40%), so the line is too optimistic at the
low end, but only ~115 of 1,169 players are there and the curve's errors on healthy players cancel the gain.

Flagged-out players (0 projected games, or OUT with no projection) in this population: 40, who played 28% of games
(23 of 82). `ESPN_OUT_GAMES` was 14, from a narrower group (15 players with 20+ mpg); it is changed to 23 to match the
population the app applies it to. Calibration, not a test.

## Addendum: low-end-only correction (designed after seeing the table above, so weaker evidence)

**C2:** players ESPN projects under 60 games (or flagged out) get the leave-one-season-out average share of such players
in the other three seasons; everyone else keeps C0. Same adoption rule, against C0 with `ESPN_OUT_GAMES` = 23.

**C2 result: fails.** 97 low-end players; squared error 0.0585 -> 0.0577 (interval -0.0031 to +0.0013), better in 1 of 4
seasons (all of the gain from 2025-26), stars worse (+0.0075; low-projected stars played more than the average injured
player). Nothing changes: ESPN's projected games already carry most of the injury news that can be extracted from them.
