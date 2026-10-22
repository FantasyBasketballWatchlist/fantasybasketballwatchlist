# Preregistration: the draft suggestion on past seasons, scored by real games

Written 2026-10-22, before any result. Code: `analysis/draft_backtest.py` (data prep and scoring) and the draft page's own
engine (`templates/draft.html`) run in the browser on past seasons' players; results in `analysis/draft_backtest.json`.

## Why

The earlier draft tests (docs/prereg-draft-opponents.md, docs/prereg-draft-suggestion-v2.md) scored rosters with our own
projections. Here the score is what the drafted players actually did.

## Seasons and players

2021-22, 2023-24, 2024-25, 2025-26 (the seasons with genuine ESPN preseason projections, as in analysis/test_ten_team.py).
Pool: as in that test (players with 20+ games the season before who played again; rookies aren't in it). Our values: the
app's preseason hybrid BPV ("BPV + ESPN hybrid (app)" in test_ten_team; its constants were chosen on these seasons, a
known in-sample advantage). Positions: ESPN's eligibility for that season (the archived kona data).

## Draft

10 teams, 13 rounds, snake, ESPN lineup PG, SG, SF, PF, C, G, F, UTIL x3. The other 9 teams take the first available
player by ESPN's preseason projected total, unless one of their next 6 fills a starting spot they can't fill yet. Our
team, from each seat 1-10, drafts by:

- **Engine:** the current suggestion (`lookAhead`), unchanged.
- **Best BPV:** the best BPV left.
- **ESPN:** like the other teams (reference).
- **A, B:** the engine with injury-aware nights / opponents reaching 12 (both lost in docs/prereg-draft-suggestion-v2.md).

## Score (real games only)

For every date of the regular season: our players who played that day fill the lineup, best preseason BPV first
(dual-position players move to where they help; what a manager could know in advance); the score is the starters'
actual fantasy points. Season score = the total. Secondary: best-10 season totals (as in test_ten_team).

## Questions and pass rules (judged once)

1. **Engine vs Best BPV** (does the positional look-ahead help?): engine better on the mean season score over 40 drafts
   (4 seasons x 10 seats) **and** in at least 3 of 4 seasons.
2. **Engine vs ESPN** (is the suggestion better than drafting like everyone?): same rule.
3. A and B vs the engine: reported, and kept only if they pass the same rule against the engine.

## Known limits

No in-season moves (waivers, trades, streaming); opponents are modeled, not real; four seasons; the hybrid's constants
were tuned on these seasons; pool excludes rookies.

## Result (2026-10-22)

`analysis/draft_backtest.json` (rosters: `analysis/draft_backtest_rosters.json`). The drafts ran on the page's own script
under Node (the browser extension was unavailable): same code. Season score (real starters' FPTS), mean of 10 seats:

| Season | Engine | Best BPV | ESPN | A | B |
|---|---|---|---|---|---|
| 2021-22 | 26,454 | 25,024 | 25,819 | 27,732 | 26,181 |
| 2023-24 | 29,748 | 29,186 | 29,488 | 29,164 | 30,016 |
| 2024-25 | 28,141 | 26,978 | 27,987 | 27,678 | 28,237 |
| 2025-26 | 22,495 | 23,654 | 25,850 | 21,512 | 22,798 |

1. **Engine vs Best BPV: passes** (+499 per season, better in 3 of 4; noisy: about 1.5 standard errors).
2. **Engine vs ESPN: fails** (-577; better in 3 of 4, but 2025-26 -3,356). In 2025-26 every engine seat drafted Jayson
   Tatum early (41.8 BPV in the backtest pool, which doesn't apply known offseason injuries; torn Achilles, no ESPN
   projection, 16 games). Side check, not judged: without Tatum, 2025-26 is engine 24,864 vs ESPN 25,850, and the
   four-season mean is about even.
3. **A fails** (-188, 1 of 4). **B passes its rule** (+99, 3 of 4) but by about 0.5 standard errors, and it lost in the
   simulated test (docs/prereg-draft-suggestion-v2.md); shipped because the rule was met.

Guards drafted (of 13): engine 5.7-7.4 by season, similar to ESPN-style drafting (6.1-6.6).
