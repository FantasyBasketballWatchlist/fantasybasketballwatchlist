# Round 10 pre-registration (written 2026-09-29, before any of these tests were run)

Source of the ideas: reports/Beating fantasy basketball projections.md (seven-item shortlist).
Seasons scored: 2021-22, 2023-24, 2024-25, 2025-26 (the four with genuine ESPN preseason projections
and archived FantasyPros ECR). 2022-23 is excluded (no preseason ESPN projection).

## Common protocol (every item)

- **Baseline** = the app's current preseason formula ("blend"): production = 62.5% BPV (last season +
  age curve + roster crowding) + 37.5% ESPN per game; games = ESPN projected games x 0.86 (BPV's own
  availability when ESPN has no projection).
- **Pool** (fixed, per season): union of the preseason top 150 of BPV-blend, ESPN projections and ECR,
  plus the actual top 150. Players who then missed the season stay in with 0 actual points.
- **Primary metric**: absolute error of projected season FPTS total (ESPN default points).
  Secondary: per-game absolute error (players with 20+ games), Spearman rank correlation, and
  draft-simulation Design B (one team uses the list, nine draft by ESPN projections).
- **Every fitted number** is fitted leave-one-season-out (LOSO) or on seasons before 2019-20.
- **Paired per-player differences** (variant error minus baseline error), 95% bootstrap interval
  resampling players (clustered by player across seasons), 2,000 resamples.
- **Adoption rule**: a variant is adopted only if (a) it beats the baseline on the primary metric in at
  least 3 of 4 seasons, (b) its paired interval is entirely below zero after a Holm correction over all
  adoption candidates in this round, and (c) it is not worse than the baseline for the actual top 50
  (paired mean difference <= 0).
- **Timing caveat** (cannot be fixed with archived data): ECR snapshots are from 1 day to 8 weeks before
  opening night; ESPN's projections are its final preseason values. Same-date capture happens for
  2026-27 prospectively.

## Items and variants (at most three each; nothing added after seeing results)

1. **Three-source blend** (ECR rank -> points via a curve fitted LOSO: isotonic, decreasing in rank,
   separately for season total and for per game).
   - 1A baseline. 1B equal thirds of season totals: BPV (no ESPN) / ESPN / ECR.
   - 1C 0.25 BPV / 0.25 ESPN / 0.50 ECR. Missing source for a player -> weights renormalized.
2. **Gap decomposition** (diagnostic, no adoption): baseline vs ECR error split into per-game and games
   parts, and by slice: team changers, preseason injury news (ESPN projects < 60 games), second-year
   players, age <= 23, age >= 32, actual top 50.
3. **Minutes from ESPN, rate from BPV**: rate = BPV production / last season's minutes per game.
   - 3A baseline. 3B rate x ESPN projected minutes. 3C rate x (50% last season's minutes + 50% ESPN's).
   - Games as in the baseline. Primary metric per game (this item changes per-game only), totals secondary.
4. **Slice weights**: weight on outside sources raised for team changers, second-year players and
   injury-news players, each chosen LOSO from {base, base + 0.15, base + 0.30}; base = item 1's winner
   (or the baseline's 37.5% if nothing wins item 1). One adoption candidate.
5. **Per-stat fitted rates**: per-minute rate of each scoring stat with its own days-based decay and its
   own padding toward the league-average rate, both fitted by optimizer on targets 2012-13..2018-19
   (never on scored seasons). FPTS rate = scoring-weighted sum.
   - 5A BPV's per-minute production (last season + age). 5B fitted per-stat rates + the same age curve.
   - Scored first with minutes held at actual (rate side only), then as a full projection.
7. **Per-stat aging** (inside item 5's bundle): 5C = 5B with per-stat per-minute age deltas (fitted on
   2010-11..2018-19 pairs) instead of the total age curve.
6. **Rookie prior**: rookies' first-season FPTS per game (20+ games), LOSO across 2010-11..2025-26.
   - 6A current draft-range baseline. 6B regression on log(pick) and age (undrafted = bucket mean).
   - 6C 25% 6B + 75% ESPN per game (ESPN seasons only).
