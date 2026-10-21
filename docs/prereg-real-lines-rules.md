# Preregistration: a bet-selection rule set for player props

Written 2026-10-21. The rules come from reasoning about the model's blind spots and how prop markets work (see the
conversation summary below), not from searching the 2024-25 results; a few numbers (the blend weights, the shape's
variance multiplier) were fitted on 2024-25 November-December. They are frozen here.

**Design reference:** 2024-25, 2024-11-06 to 2025-01-29 (already seen; reported for reference only, not a test).
**Test:** fresh lines the model and these rules have never touched: **2023-24 and 2025-26**, same markets and snapshot
time as before (an hour before tip-off), downloaded only after this file is committed. Code: `analysis/real_lines_rules.py`.

## The probability

1. The single-game projection's mean and variance (`game_projections.FIX`, as backtested), with a **normal** shape
   and the variance x 1.4 (points, rebounds, assists), at the line.
2. Blended with the market: logit(p) = logit(market) + w x (logit(model) - logit(market)), w = 0.10 points,
   0.20 rebounds, 0.30 assists. "Market" = the books' chance of the over at the consensus line, from the median prices
   with the margin removed proportionally.

## The bet (all must hold)

- **R1, best price:** price = the best (highest decimal) among books offering the consensus line, for the chosen side.
- **R2, value:** expected profit at that price (with the blended chance) of at least **3%**; the side with the higher
  expected profit.
- **R3, no fresh injury news:** skip every prop in a game where a rotation player (20+ minutes a game over his last 10
  games) on either team who played his team's previous game is listed Out, Doubtful or Questionable on that day's
  official injury report.
- **R4, no wild disagreement:** skip if the model's own chance (before blending) differs from the market's by more
  than 0.15.
- **R5, blowouts:** skip overs when the game's point spread is 12 or more (consensus spread, same snapshot rules).

Every bet is $1.

## Pass rule (test seasons)

ROI above 0 with the 95% interval (bootstrap over game days) above 0, over both test seasons together, **and** ROI
above 0 in each of the two seasons.

## Reported, not part of the verdict

Each rule's contribution (ROI with that rule removed); overs vs unders; role players (under 20 minutes a game) vs
starters; by stat; the same bets at median prices (to separate the model from the shopping).

## Why these rules (summary)

The model doesn't know when teammates are out (R3), projects hours before tip-off while lines absorb late news (R3),
ignores game context like blowouts (R5), and its biggest disagreements with the books were its worst calls (R4).
Shopping the best price is arithmetic: across 2024-25 it cut the books' two-sided margin from 6.8% to 3.5% (R1).
Sportsbook lines are sharper than the model on their own, so the market is the base and the model only nudges it.

## Amendment (2026-10-21, before any test-season data was downloaded)

R1 now shops **only US state-licensed books** (DraftKings, FanDuel, BetMGM, Caesars, BetRivers, ESPN Bet, Fanatics,
Bally, Hard Rock, betPARX); props with no licensed price are skipped. Reason: on the 2024-25 reference data about 18%
of the best prices came from offshore books (Bovada, BetOnline), which aren't legal in US states, and the bets have
to be placeable. The market's median price still uses every book.
