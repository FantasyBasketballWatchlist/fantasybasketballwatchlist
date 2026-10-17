# Holdout test on untouched seasons: rules written before running

*Written 2026-09-28, before any data from these seasons was downloaded or looked at.*

## Why

Every BPV decision so far (about 105 tested ideas) used the 2019-20 to 2025-26 seasons. Some of the
additions may have passed by luck. The 2014-15 to 2018-19 seasons were never used for anything, so
running today's formula on them, unchanged, is a fresh test available now.

## Rules

- **Target seasons:** 2014-15, 2015-16, 2016-17, 2017-18, 2018-19. Earlier seasons (from 2009-10) are
  used only as history, the way the app uses past seasons.
- **Frozen formula:** every constant as in `ratings.py` on 2026-09-28 (age curve, crowding −0.0177,
  early-season prior 8 games / rookies 10, availability decay 0.5 and 123 games, recent form 0.3 / 0.1,
  recalibration 2.964 + 0.910 × projection, shooting regression −1.85 toward the player's own last-season
  eFG%, absence streak +0.0075 − 0.0242 per game). Nothing is refitted on these seasons. League-level
  values the app computes from past data (league availability, IR share, replacement level, rookie
  baselines) are computed the same way from seasons before each target.
- **Can't be tested here:** the ESPN blend (no archived projections), official injury-report features
  (reports start 2021-22), rookie preseason minutes, the new-role rule.
- **One look:** results are reported whatever they show. The only change allowed afterward: an addition
  that is **worse than the version without it in 3 or more of the 5 seasons** on its primary measure is
  removed. Nothing else is tuned on these seasons.

## Tests and pass criteria

**Preseason** (players with 20+ games the season before; a player who then misses the season counts as 0):
models are last season's total FPTS (naive), the original formula (80/20 × career GP%), revised BPV
(availability only), and full BPV (+ age curve + roster crowding).

- P1: full BPV has a higher rank correlation with actual season totals than the naive ranking in 4+ of 5 seasons.
- P2: same against the original formula, 4+ of 5.
- P3 (additions: age + crowding): full BPV beats revised BPV on rank correlation in 3+ of 5 seasons, and
  on per-game error (players with 20+ games in the target season) with a 95% interval excluding 0.
- P4: full BPV's simulated drafts (1,000 per season, standard five-strategy field) beat the naive and the
  original formula in 3+ of 5 seasons.

**In season** (weekly checkpoints from 4 weeks in; players with 10+ games before and after, 12+ minutes):
predicting rest-of-season FPTS per game.

- P5: frozen in-season BPV (recent-form split, early prior, recalibration, shooting regression) beats the
  original 80/20 in 4+ of 5 seasons, with a pooled 95% interval excluding 0.
- P6 (additions): recalibration and shooting regression each improve on the version without them in 3+ of 5.
- P7: early season (checkpoints with 1–20 games played): the age-adjusted last-season prior beats the
  season-to-date average in 4+ of 5.

**Availability**

- P8: the recent-weighted, shrunk estimate beats career GP% for next-season availability in 3+ of 5.
- P9 (addition): the in-season absence-streak adjustment lowers squared error in 3+ of 5.

A pass on P1, P2, P5, P7 and P8 means the core method holds up on seasons it has never seen. P3, P4, P6
and P9 check the recent additions specifically, which are the ones most exposed to luck.

## Addendum (2026-09-28, written before running): ESPN blend on 2018-19 and 2020-21

ESPN's archive also serves genuine preseason projections for 2018-19 and 2020-21 (checked: DeMarcus
Cousins 43 games for his known Achilles, Victor Oladipo 80 despite his January injury; Klay Thompson 0 after
his pre-season Achilles, Jamal Murray 65 despite his April ACL). 2017-18 is excluded (Gordon Hayward
projected for 0 games after his opening-night injury, so it was updated after the season began), and
2019-20 is unusable (median 0 projected games). The blend's settings were fitted on 2021-22 to 2025-26
only. The frozen versions:

- BPV: last season FPTS/game + age curve + roster crowding; games = availability estimate × team games.
- ESPN: ESPN's FPTS/game × ESPN's games.
- Hybrid (the app): 62.5% BPV + 37.5% ESPN per game; games = min(team games, 0.86 × ESPN's games).

Pool: players with 20+ games and 15+ minutes the season before and an ESPN projection (0 if they missed the
season). Criteria, in each of the two seasons:

- E1: hybrid per-game error below both BPV and ESPN (players with 20+ games in the season).
- E2: hybrid rank correlation with actual totals above ESPN's and BPV's.
- E3: hybrid error on season totals below ESPN's.
- E4: hybrid's simulated drafts beat ESPN's.

The blend counts as confirmed if E1 and E2 hold in both seasons, and as contradicted if the hybrid ranks
below ESPN or BPV in both. Two seasons are weak evidence either way. Note: the frozen age curve was fitted
on data that included 2020-21, a small advantage for BPV and the hybrid in that season.
