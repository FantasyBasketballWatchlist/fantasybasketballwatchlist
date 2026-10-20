# Preregistration: players with a short or missing recent history

Written 2026-10-20, before any result was computed. Script: `analysis/short_history.py` (results in
`analysis/short_history.json`). These rules went live on 2026-10-20 without a test, as stopgaps for values that were
clearly wrong (5 games ranking a player 60th, 2 games ranking one 68th). This checks them against what they replaced.

## T1. Between seasons: under 20 games last season

- Target seasons 2011-12 to 2025-26. Players with 1-19 games in S-1 and 20+ games over S-2 and S-1 together, who
  then played 10+ games in S. Target: FPTS per game in S, weighted by games in S.
- **P0 (before):** his S-1 average. **P1 (now):** S-2 and S-1 games pooled, plus the age-curve adjustment when the
  pooled minutes are 15+ per game. Reported, not judged: **P2**, his S-2 average plus age.
- The ESPN blend is left out (ESPN data covers only four seasons); both P0 and P1 would get the same blend.

## T2. Almost no NBA history: blend toward the draft-slot baseline (k = 10 games, as for rookies)

- **T2a, between seasons:** target seasons 2011-12 to 2025-26; players with 1-19 games in S-1 and under 20 over S-2 and
  S-1 together, not in their first season, who played 10+ games in S. P0: S-1 average. P1: shrunk toward the average
  rookie from his draft range (undrafted: the undrafted baseline), baselines from the five seasons before S.
- **T2b, in season:** checkpoints 14, 28, 42, 70 and 100 days after each opener, 2011-12 to 2025-26. Players not in
  their first season, under 20 games last season and under 20 over the last two, with 1-19 games so far, who play 5+
  more. P0: BPV's in-season production from his games so far with no prior. P1: the same shrunk toward the draft-slot
  baseline. Target: FPTS per game for the rest of the season, weighted by those games.

## T3. In season: under 20 games last season, 20+ over the last two

- Same checkpoints and seasons as T2b. Players not in their first season, 1-19 games last season, 20+ over the last
  two, with 1-29 games so far, who play 5+ more. P0 (before): BPV's in-season production with no prior.
  P1 (now): shrunk with the pooled last two seasons (+ age) as the prior, k = 8 games (the prior weight BPV uses for
  last season).

## Adoption rule for each (fixed now)

The rule (P1) stays if, against P0, its absolute error is lower pooled with a 95% interval (bootstrap clustered by
player) that excludes zero, and it is better in at least 60% of the seasons with cases. Squared error is reported too.
If a rule fails, P0's behavior is not simply restored when P0 is the "clearly wrong" raw average: the result decides
between the alternatives tested here (for T1, P2 is the fallback if it beats both).

## T4. Returners with the ESPN blend (no verdict)

Players back from a whole missed season in the four seasons with genuine preseason ESPN projections (2021-22,
2023-24 to 2025-26) are too few for a test. Their errors with and without the blend are listed only.

## Result (added after running it, 2026-10-20)

`analysis/short_history.json`. All four rules pass and stay: T1 6.50 -> 5.32 (interval -1.97 to -0.41, 14 of 15
seasons); T2a 6.86 -> 5.57 (15 of 15); T2b 5.55 -> 4.74 (14 of 15); T3 4.97 -> 4.22 (11 of 15). Squared errors fell more
(T1 72 -> 44). P2 (season before only) lost to P1 (3 of 15). T4: 6 returners with an ESPN projection, no verdict.
