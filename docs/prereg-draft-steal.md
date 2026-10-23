# Preregistration: take someone else now when the suggested player will likely last ("steal")

Written 2026-10-22, before any result. Code: the draft page's engine (`templates/draft.html`, `STEAL`), run on the page's
own script under Node; results in `analysis/draft_steal.json`.

## Why

A user's suggestion at pick 78 was a player ESPN ranks about 94th, with their next pick at 82. Two earlier tests
(docs/prereg-draft-opponents.md, docs/prereg-draft-suggestion-v2.md) modeled every other team as drafting by ADP for the
whole play-out and lost. This is narrower: only the suggested player, and only his chance of lasting to the next pick.

## Rule (on the clock, with a next pick)

- T = the engine's suggestion. p = chance T is still there at the next pick N: 1 - Phi((ln(N / ADP_T) - mu) / sd), where
  ln(actual pick / ADP) ~ Normal(mu, sd) in real drafts (mu, sd fitted on the design leagues' picks).
- For every other shortlist candidate c: value = p x (roster with c now and T at N, rest played out) + (1 - p) x
  (c now, rest played out as usual). If the best such value beats T's, suggest c ("take c now; T has a p% chance of
  lasting to your next pick").
- Players without ADP: no steal.

## Replay and score

As in docs/prereg-draft-suggestion-v2.md: each league, each slot 1-10, our team follows the suggestion; the others take the
first available player in the league's actual pick order unless one of their next 6 fills an open starting spot. Score:
the same 400-night season simulation (per-game production, availability, ESPN slots, empty spots 0). Note: the real
room, not ADP, decides whether T actually lasts.

- **Design** (fit mu, sd; a sanity check): 538977698, 1854297225, 1503540199.
- **Test (once):** 34650931, 1192115637, 2029687819 (never used).

## Pass

On the test leagues: mean score above the current engine over the 30 slot-drafts **and** above it in at least 2 of 3
leagues. Reported: how often a steal was suggested and how often T actually lasted.

## Known limits

Scored with our projections (the question is the room, which the real picks supply); ratings are today's, the drafts were
1-2 days earlier; ADP is ESPN's season ADP (includes drafts after these).

## Result (2026-10-22)

`analysis/draft_steal.json`. mu = -0.095, sd = 0.211 (385 design-league picks: real picks come ~9% before ESPN ADP).
Design leagues (sanity check): -0.25 per night, better in 12 of 30. **Test leagues: +0.17 per night, better in 16 of 30,
higher in 2 of 3 leagues (+0.83, +0.52, -0.84): passes; shipped.** Over all six leagues it's about even (-0.04). Steals
were suggested about 4 times per draft and the waited-on player ended up on our team about 40% of the time, so the
lasting chance from ADP is optimistic or the engine changes its mind at the next pick. ADP is now in /api/rankings.

## Calibration fix (2026-10-23; not a new test)

The first harness wasn't saved; rebuilt as `analysis/draft_steal_data.py` (inputs), `analysis/draft_steal_replay.js`,
`analysis/draft_steal_calib.py`, `analysis/draft_steal_summary.js`. Today's ratings and ADP, so numbers differ from above.

- **The lasting chance was too low, not too high.** On the six real drafts (every slot's pick, the top 10 left by BPV
  with an ADP, did he last to that slot's next pick): when the normal formula said 0.40 he lasted 0.50, 0.59 -> 0.82,
  0.80 -> 0.89. It ignores that a player still there past his ADP tends to keep sliding. Replaced with a logistic in
  ln(next / ADP) and ln(now / ADP), fitted on all six (-0.334, -13.743, 1.751). Cross-fitted (each half of the leagues
  scored by the other half's fit) it's better calibrated: 0.40 -> 0.36, 0.60 -> 0.70, 0.80 -> 0.84; Brier 0.121 vs
  0.136.
- **The "40% ended on our team" was the engine changing its mind**, not players being taken: in the replay 99 of 158
  waited-on players lasted and 71 were taken. The page now follows through: at the next pick it suggests T if he's
  there (the steal's value assumed that). The plan is kept in the draft state.
- **Value (replay, 60 slot-drafts, vs no steal):** first version +0.17 per night (better in 28, worse in 23); with the
  logistic and follow-through +0.21 (27 better, 22 worse; per league +0.55, -0.20, +0.17, +0.35, -0.29, +0.69). Within
  the noise: not evidence that stealing helps, and these leagues are no longer untouched (the fit used them). The page's
  own code reproduces the harness's logistic + follow-through run exactly (0 of 60 drafts differ).
- In the replay the room lasts longer than the real one (when our pick differs from the real pick at our slot, every
  later pick shifts back one), so replay lasting rates run above the real-draft calibration.
