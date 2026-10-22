# Preregistration: availability for veterans ESPN doesn't project

Written 2026-10-22, after seeing only the group sizes and mean games shares below, before fitting or testing anything.
Code: `analysis/no_espn_availability.py` (results in `analysis/no_espn_availability.json`).

## Why

Before a season, veterans' availability comes from ESPN's projected games. When ESPN has no projection (often an
offseason injury, like Jayson Tatum's torn Achilles before 2025-26), BPV falls back to the player's own history, which
can't see the injury. Looked at before writing this: such veterans (15+ mpg last season, in the BPV pool) played 0.62,
0.62, 0.58 and 0.46 of their team's games in 2021-22, 2023-24, 2024-25 and 2025-26, while our history-based estimate
averaged 0.65-0.73.

## Change

For those players (preseason only, and the early-season blend that uses ESPN's preseason games): availability =
history-based estimate x s, with s = (total actual share) / (total estimate) over the design seasons' no-projection
veterans. The site also flags them ("no ESPN projection: check injury news").

## Test (once)

Design: 2021-22, 2023-24, 2024-25 (fit s). Test: 2025-26. Measure: mean absolute error of availability (games played /
team games) for that season's no-projection veterans, scaled vs unscaled. **Pass:** lower error. Reported: the same on
the design seasons, and the mean signed error.

## Known limits

Small group (14-54 players a season, 28 in the test season); one test season; the group mixes injured players with
players ESPN dropped for other reasons (lost roles), so s is an average over both.
