# Preregistration: draft suggestion, injuries/depth and positional runs

Written 2026-10-22, before any result. Code: the draft page's engine (`templates/draft.html`), replayed in the browser;
results in `analysis/draft_suggestion_v2.json`.

## Why

A user drafted five guards in six picks and the suggestion still named a guard. The engine scores a roster by its daily
lineups with every player playing a fixed half of the nights and injuries only averaged into his value (BPV), and it
assumes the other teams take the best BPV left unless one of their next 6 fills a starting spot. Two candidate changes.

## Candidates

- **Current (C0).**
- **A, nights with injuries:** in the engine's roster score, a player's value on a night is his per-game production, and he
  misses each night with probability 1 - his availability (fixed per player and pattern), so rosters stacked with
  injury-prone players, or thin at a position, leave starting spots empty.
- **B, positional runs:** in the play-out, other teams look up to 12 players down (not 6) for a starting spot they can't
  fill yet.
- **A+B.**

## Score (the same for every version; not any version's own objective)

A season of 400 nights: each night each rostered player has a game with probability 0.5 and, if so, plays with
probability = his availability (seeded random numbers, identical across versions); the best lineup by per-game
production starts (ESPN slots PG,SG,SF,PF,C,G,F,UTIL x3; dual-position players move); empty spots score 0. Score = mean
nightly starting production of our 13-player roster.

## Replay

As in docs/prereg-draft-opponents.md: each league, each slot 1-10, our team follows the suggestion and the other teams
take the first available player in that league's actual pick order unless one of their next 6 fills an open starting
spot.

- **Design:** 538977698, 1854297225, 1503540199. **Test:** 34650931, 1192115637, 2029687819 (not used in any test so far).

## Rules

1. On the design leagues, pick the candidate (A, B or A+B) with the highest mean score over the 30 slot-drafts; if none
   beats C0, stop (nothing shipped).
2. **Test (once):** the chosen candidate vs C0 on the test leagues. **Pass:** higher mean over the 30 slot-drafts **and**
   higher in at least 2 of the 3 leagues. Reported: guards drafted per team (mean), per-league means.

## Separately (a bug fix, shipped regardless)

When it isn't the user's pick, the suggestion was computed as if they picked now. It will instead play the other teams
forward (the engine's own opponent model) to the user's next pick and suggest from who's likely left there.

## Known limits

Per-game production and availability are our own estimates (the score inherits their errors); empty starting spots score
0 (in practice a manager can stream a free agent into a long-term hole); real rooms' picks can't react to ours.

## Result (2026-10-22)

`analysis/draft_suggestion_v2.json`. **Stopped at rule 1: no engine change shipped.** Mean season score over the 30
design slot-drafts: current 178.70; A 178.13 (better in 13 of 30); B 177.80 (9 of 30); A+B 178.27 (12 of 30). The test
leagues were not run. The current engine drafts about 7 guard-eligible players of 13 and still scored best: in ESPN's
lineup (PG, SG, G and three UTIL spots) guards can fill 6 of 10 starting spots, the top of the BPV board is guard-heavy
(27 of the top 50 are guard-eligible vs 21 forward and 13 center), and forwards and centers at the user's later picks
were close enough in value. The off-the-clock bug fix shipped.
