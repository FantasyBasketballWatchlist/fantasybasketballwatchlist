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
