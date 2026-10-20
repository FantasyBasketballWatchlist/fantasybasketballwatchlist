# Preregistration: production after returning from an injury absence

Written 2026-10-20, before any result was computed. Script: `analysis/injury_return.py` (results in `analysis/injury_return.json`).

## Question

Does a player produce less (FPTS per game) after coming back from a long absence than BPV currently projects, and
should BPV adjust for it? Published studies say yes for the worst injuries (Achilles repair: PER about 80% of the
pre-injury level and minutes about 83% in the first season back, vs 96% and 103% for matched controls, Khalil et al.;
ACL reconstruction: a first-season dip, mostly recovered by the second season). These are small samples of players
who made it back, from the most serious injuries only. BPV needs the effect for every absence, measured against its
own projection.

## Test A: back from an absence during the season

- Events, 2009-10 to 2025-26: a player with 10+ games and 20+ minutes per game this season misses 5+ team games in a
  row, then plays again with 10+ of his team's games left. Each such absence is one event.
- Baseline: BPV's in-season production at the moment he returns, built from his games before the absence exactly as
  `ratings.build` does (season + recent form, last-season prior with age, recalibration, shooting regression). No
  preseason prior (not saved for past seasons), as in the earlier in-season tests.
- Target: his actual FPTS per game in the rest of that season after the return (3+ games needed), weighted by those games.
- Also scored at a second checkpoint, 5 games after the return (the baseline then includes those 5 games).
- Candidates, each fitted leave-one-season-out (multiplier = games-weighted actual / baseline in the other seasons):
  1. one multiplier by absence length: 5-9, 10-19, 20-39, 40+ team games;
  2. (1) split by age (30+ vs under 30);
  3. (1) split by injury type from the official injury report (serious vs other), 2021-22 to 2025-26 only.

## Test B: back from a whole missed season

- Events, 2011-12 to 2025-26: 20+ games and 15+ minutes per game in season S-2, no games in S-1, 10+ games in S.
- Baseline: what the app does now (`ratings.py`, returners): the S-2 average plus the age-curve adjustment.
- Target: FPTS per game in S. Candidate: one multiplier, fitted leave-one-season-out.

## Adoption rule (fixed now)

A candidate is added only if, against the baseline, out of sample:

1. its games-weighted absolute error is lower pooled over all events, with a 95% interval (bootstrap clustered by player)
   that excludes zero;
2. it is better in at least 60% of the seasons that have events (seasons where both are tied count as not better);
3. it is not worse for stars (baseline 40+ FPTS per game).

Candidate 2 or 3 is added only if it also beats candidate 1 by the same rule. If nothing passes, nothing changes and
the result is reported in the methodology's Section 16 table like every other rejected idea.

## Known limits

- Every season used here has been used before for other tests. This question has not been tuned on them, but it is
  not a clean holdout.
- Absences of 5+ games by 20+ mpg regulars are mostly injuries, but some are suspensions, personal leave, trade
  holdouts or the 2019-20 bubble opt-outs. Before 2021-22 there is no report to tell them apart.
- Players who never came back that season are not events, so this measures production when playing, not availability.
