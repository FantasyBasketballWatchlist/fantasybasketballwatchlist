# Preregistration: sportsbook lines and recent minutes in BPV's in-season production

Written 2026-10-21, before any result. Code: `analysis/bpv_market.py` (results in `analysis/bpv_market.json`), using
`analysis/bpv_replay.py` (the app's `ratings.build` replayed as of past dates: only games and the injury report known
by then).

## Why

The betting work found that (1) sportsbook prop lines predict a player's next game better than our model (they know
about roles, minutes and injuries sooner), and (2) recent minutes carried more information than BPV's season-long
averaging assumes. Either could sharpen BPV's rest-of-season production.

## Data

2024-25. BPV replayed on Mondays: **design** 2024-12-02, 12-09, 12-16, 12-23, 12-30; **test** 2025-01-06, 01-13,
01-20, 01-27. Prop lines: `data/lines/history.csv` (points, rebounds, assists, an hour before tip, 2024-11-06 on).

## Candidates (applied to BPV's in-season `production`, FPTS per game if he plays)

- **R, recent minutes:** production x (w x his minutes per game with a 3-game half-life + (1 - w) x his season
  minutes per game) / season minutes per game, this season's games before the date; w in {0, 0.25, 0.5, 0.75}.
- **M, market:** for players with lines on 3+ games in the 14 days before the date: market PRA = the mean over those
  games of the consensus lines' sum (points + rebounds + assists; consensus = the line most books offer), times kappa
  (actual PRA / line PRA over all November-December player-games with lines: lines sit near the median, below the
  mean). Production + lambda x (market PRA - his season PRA per game before the date) x his season FPTS per PRA;
  lambda in {0, 0.25, 0.5, 0.75, 1}.

Chosen in that order on the design dates by the pooled mean absolute error of production vs his actual FPTS per game
over the rest of the season (players with 10+ games after the date); each kept only if it lowers it.

## Test (once)

On the test dates, the chosen version vs the app's current production. **Pass:** lower pooled mean absolute error and
lower on at least 3 of the 4 dates. Reported: the same for players with market lines only; rank correlation of BPV
(with the new production) with rest-of-season total FPTS.

## Known limits

One season, two months of lines (points, rebounds, assists only; no threes, steals, blocks or turnovers). The lines
are an hour before tip; in the app they'd come from the forward collection (`data/lines/live/`), so adoption also needs
that collection kept running (Odds API credits or PropLine).

## Result (2026-10-21)

`analysis/bpv_market.json`. **Neither kept** (both made the design dates worse at every setting): mean absolute error
of rest-of-season FPTS per game, current 3.824; recent minutes 3.842-4.002; market 3.844-4.077. The test dates are
unchanged (3.973; rank correlation with rest-of-season totals 0.782). Short-term signals (a few games of minutes, two
weeks of lines) help a single game but over-react for the rest of a season; BPV's shrunk season-long production is
already better calibrated for that horizon.

## Addendum: teammate absences (written 2026-10-21, after the result above, before this was computed)

- **T:** each team's rotation players (20+ minutes a game this season before the date) listed Out on that day's
  injury report vacate minutes for the rest of the season: V = sum of (their minutes per game x (1 - their BPV
  availability)), i.e. the share of the remaining games they're expected to miss. A teammate's production x
  (1 + alpha x V x his share of the team's active minutes / his minutes per game); alpha in {0, 0.25, 0.5, 0.75, 1}.
- Same dates, same error measure, same pass rule (chosen on the design dates, kept only if it lowers the error; test
  on the four January dates: lower pooled and on 3 of 4).

## Addendum result (2026-10-21)

`analysis/bpv_teammates.json`. **Not kept**: every alpha above 0 made the design dates worse (3.769 at 0; 3.800 /
3.840 / 3.896 / 3.968 at 0.25-1). Test dates unchanged (3.872; rank correlation 0.795). Players with an injured rotation
teammate are harder to project (error 4.26 vs 3.87 overall), but scaling up their minutes doesn't help: by the time a
teammate is listed Out for a long stretch, the player's season-to-date numbers already partly reflect it, and minutes
gained in a teammate's absence come with a lower rate per minute.
