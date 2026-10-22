# Preregistration: modeling other drafters in the draft suggestion

Written 2026-10-22, before any result on the leagues below. Code: the draft page's own engine (`templates/draft.html`:
`lookAhead`, `playOut`, `opponentPick`, `dailyValue`), replayed in the browser; results in
`analysis/draft_opponents.json`.

## Background

The suggestion plays out the rest of the draft assuming the other teams take the best BPV left (unless one of their next
few fills an open starting spot). An earlier try (2026-10-22) assumed they draft by ESPN's average draft position (ADP)
instead: it helped in synthetic drafts (+0.8 to +1.6 BPV per night) but lost -0.8 when replaying one real draft (league
538977698), so it wasn't shipped. Six finished public ESPN drafts are now available (10 teams, H2H points, standard
lineup, 13 rounds).

## Leagues (fixed in the order the user listed them; 538977698 was already seen)

- **Design:** 538977698, 1854297225, 1503540199.
- **Test:** 34650931, 1192115637, 2029687819.

## Replay

For each league and each draft slot 1-10: our team drafts by the suggestion; every other team takes the first available
player in that league's **actual pick order** (players nobody took come after, by ADP then BPV), unless one of the next
6 fills a starting spot it can't fill yet (the same need rule as the engine). Score: the engine's `dailyValue` of our final
13-player roster (BPV of the daily starting lineups, averaged over game-night patterns). Today's ratings (a known limit:
the drafts happened 1-2 days earlier; BPV changed little).

## Candidates (opponent order assumed by the suggestion)

- **Current:** best BPV left.
- **A:** ESPN ADP (players without ADP after, by BPV).
- **S:** ESPN's STANDARD draft rank (the list ESPN's autodraft and default draft queue follow).

## Rules

1. On the design leagues, pick A or S by the mean absolute log(actual pick / key) over all 390 picks (which one predicts
   real picks better).
2. Replay the chosen one vs current on the design leagues (30 slot-drafts). If its mean is not above current's, stop: not
   shipped.
3. **Test (once):** the same on the test leagues. **Pass:** mean gain over current > 0 across the 30 slot-drafts **and**
   positive in at least 2 of the 3 leagues. Reported: per-league means, number of slots better/worse.

## Known limits

Scored by BPV itself (the question is only whether the suggestion uses BPV better given how the room drafts). Opponents'
actual order is one realization; when our picks differ from the real team's, the room's later picks can't react. Six
leagues, some drafted by the user and friends (who may use this site).

## Result (2026-10-22)

`analysis/draft_opponents.json`. Rule 1: ADP predicts the design leagues' picks better than ESPN's STANDARD rank (mean
absolute log error 0.157 vs 0.179), so A. Rule 2: **stopped, not shipped.** Replaying the three design leagues from every
slot, assuming ADP drafters made our final lineups 0.78 BPV per night worse than assuming BPV drafters (538977698 -0.82,
3 of 10 slots better; 1854297225 -2.01, 2 of 10; 1503540199 +0.48, 4 of 10). The test leagues were not run. Real rooms
stray from ADP enough (log SD ~0.23 in the first league) that "he'll still be there" bets lose more often than they win;
assuming the room takes the best BPV left is the more cautious plan and does better.
