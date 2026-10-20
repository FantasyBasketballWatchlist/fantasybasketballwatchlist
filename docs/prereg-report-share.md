# Preregistration: how an Out listing changes a player's rest-of-season availability

Written 2026-10-20, before any result was computed. Script: `analysis/report_share.py` (results in `analysis/report_share.json`).

## The problem

`REPORT_SHARE_PLAYED` (a regular listed Out with an injury plays this share of his team's remaining games, by injury
type) was fitted and tested as his share of **all** remaining games, so it already includes the ordinary absences every
player has later in the season. `ratings.build` uses it differently: it treats `(1 - share) x remaining` games as one
IR-able stretch and then applies his normal availability to the games left after that, so his expected games played
are `share x availability`. Ordinary absences are counted twice. Example: a strain listed on opening night becomes
"out 34 more games"; regulars listed that way actually missed a median of 6 in a row.

## Test

- Spells, 2021-22 to 2025-26: a regular (20+ mpg, 5+ games so far) on the official report as Out with an injury; the
  first listing after his last game is the spell's start. 10+ team games left.
- Target: share of his team's remaining games he played, weighted by the games remaining.
- His normal availability: BPV's estimate from the seasons before (`predict_availability`, as before a season; the
  in-season update isn't rebuilt for every date).
- Predictions of the share played:
  - **C0, current:** share(type) x availability, shares as in `ratings.py`.
  - **C1, fix:** share(type), refitted leave-one-season-out.
  - **C2:** share(type, games left: 10-40 / 41-60 / 61+), leave-one-season-out.
  - **C3:** availability x (1 - typical streak(type) / games left), streak = mean games missed in a row, leave-one-season-out.
- Error: absolute error of the share, weighted by games left.

## Adoption rule (fixed now)

C1 replaces C0 if, out of sample, its error is lower pooled with a 95% interval (bootstrap clustered by player) that
excludes zero, it is better in at least 3 of the 5 seasons, and it is not worse for stars (40+ FPTS per game before the
spell). C2 or C3 replaces C1 only by the same rule against C1.

## How the winner enters BPV

BPV = availability x production + missed share x (long-stretch part x replacement). For a listed player:
games played = share x remaining; the typical streak (mean, by type, capped at the games he won't play) is a known long
stretch, valued at replacement (IR him, stream someone); the rest of his missed games get BPV's usual league share of
long stretches. Only the share was tested here; the split of missed games follows BPV's existing formula.

## Result and decision (added after running it, 2026-10-20)

`analysis/report_share.json`. 2,162 spells, 2021-22 to 2025-26.

- C1 vs C0: error 0.229 vs 0.295 (-0.066, interval -0.078 to -0.054), 5 of 5 seasons, stars better (-0.086). C0 predicted
  a 38% share played on average; players actually played 58%. **The double count is real.** Passes.
- C2 vs C1: -0.001 (interval crosses zero). Fails.
- C3 vs C1: -0.009 (-0.015 to -0.002), 4 of 5, stars better: passes the rule as written. But C3 over-predicts the mean
  (63% vs 58% played), and on squared error C1 is better (0.0747 vs 0.0784, 4 of 5 seasons). BPV is an expected value,
  and this project already scores availability by squared error for that reason; choosing absolute error above was a
  mistake in this preregistration. So C3 is **not** adopted, and that choice was made after seeing the results.
- What changed in BPV: nothing new was fitted. Reading `analysis/test_availability3.py` showed the original test already
  used the share as the player's availability; `ratings.build` had implemented it differently. The build now does what
  was tested (availability = `REPORT_SHARE_PLAYED`, the original constants, fitted on every listing day, which is how the
  app applies them; on spell starts only they still beat C0: -0.050, 5 of 5, stars better). The refitted spell-start
  shares are not used, because spell starts under-represent the long injuries that stay listed for weeks.
- Untested: valuing the typical streak at replacement (IR) and the rest of his missed games at the league's usual
  long-stretch share. It follows BPV's existing formula.
