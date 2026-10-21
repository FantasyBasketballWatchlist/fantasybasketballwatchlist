# Preregistration: BPV in season vs FantasyPros' rest-of-season expert consensus

Written 2026-10-20, before any ranking page was downloaded or any result computed. Script: `analysis/ros_experts.py`
(results in `analysis/ros_experts.json`).

## Question

Before a season, FantasyPros' expert consensus (ECR) out-ranked the BPV + ESPN blend in 4 of 4 seasons. In season BPV
sees real minutes and roles within days, and it has never been compared with the experts. Is BPV better, worse, or
better combined with them?

## Data

- FantasyPros rest-of-season rankings (`/nba/rankings/ros-overall.php`, category scoring, the same kind of list as the
  preseason test), every Wayback Machine capture between 14 days after an opener and 30 days before the regular
  season's end, seasons 2021-22 to 2025-26. At most one capture per 7 days (the first), so busy weeks don't dominate.
- BPV: the app's own ratings rebuilt on the capture date (game logs cut at that date, that week's official injury
  reports), as in `analysis/early_availability.py`.

## Scoring

- Pool at each date: the union of BPV's top 150 and ECR's top 150 (chosen before any outcome is known).
- Target: realized value per remaining team game: his FPTS in his team's remaining games plus a replacement-level
  player for every absence of 5+ games (streamed from IR), divided by the team's remaining games. A player who never
  plays again scores his streamed replacement only.
- Score: Spearman rank correlation of each list with the target over the pool, per date.
- Lists: **BPV** (rank by BPV), **ECR** (rank by expert rank), **Blend** (average of the two ranks; a player missing
  from one list gets 200 there).

## Decision rule (fixed now)

The blend is worth pursuing for the site if it beats BPV on the mean correlation across dates, with a 95% interval
from a bootstrap over capture dates that excludes zero, and is better in at least 60% of the seasons with captures.
ECR vs BPV is reported the same way, with no decision attached: it says where BPV stands.

Any live use of FantasyPros data needs their permission or a licensed source; this test only decides whether that is
worth pursuing.

## Known limits

- Category rankings, not ESPN points (the points list has too few captures); the preseason test had the same mismatch.
- Capture timing is whatever the archive has; dates cluster in some seasons.

## Result (added after running it, 2026-10-20)

`analysis/ros_experts.json`. 35 captures selected, 32 usable (3 were empty page shells). A first run used only 8,
because the parser looked for "rest of season" in the first `<h1>`, which on older pages is the site's notifications
panel; it was fixed to read the page `<title>` (all 24 recovered pages are titled "Rest of Season Fantasy Basketball
Rankings | Roto / Categories"). The rule was not changed, but the 8-date numbers had been seen.

- Mean rank correlation with realized rest-of-season value: BPV 0.724, ECR 0.684, blend 0.727.
- ECR vs BPV: -0.040 (interval -0.054 to -0.025), ECR better on 6 of 32 dates, 1 of 4 seasons. **BPV ranks better
  than the expert consensus in season.**
- Blend vs BPV: +0.003 (-0.004 to +0.011), 2 of 4 seasons: **fails**. Expert data isn't worth pursuing for in-season
  rankings.
- Caveats: the expert list is for category leagues while the target is ESPN points value (the preseason test, which
  ECR won, had the same mismatch); several in-season BPV constants were fitted on 2021-22 to 2025-26, which flatters
  BPV; 30 of the 32 dates are from 2021-22 and 2022-23.
