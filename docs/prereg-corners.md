# Preregistration: searching for profitable corners of the prop market

Written 2026-10-21, before the search was run on any data. Code: `analysis/corners.py`.

## The bets

Every price at a US-licensed book (DraftKings, FanDuel, BetMGM, Caesars, BetRivers, ESPN Bet / theScore, Fanatics,
Bally, Hard Rock, betPARX) for points, rebounds and assists, both sides, at half-point lines, $1 each.

## Corners (the only ones searched)

Each bet is tagged with:
- **book**; **stat**; **side** (over / under);
- **price:** favourite (decimal under 1.87, i.e. shorter than -115), middle (1.87-2.00), underdog (over 2.00);
- **value vs the other books:** this price's expected profit against the other books' no-vig consensus on the same
  line (leave-one-out, 4+ books): under 0, 0-2%, 2-4%, 4%+;
- **line size:** low / middle / high third of that stat's lines (cut points from the discovery data);
- **model:** the single-game projection (`game_projections.FIX`) favours this side, or not.

A corner is any single tag or any pair of tags (e.g. "FanDuel + unders", "rebounds + value 2-4%").

## Measure

- **Live and past-morning data (two snapshots):** closing-line value per bet = price taken / fair closing price - 1,
  fair close = the consensus of every book's no-vig chance at the closing snapshot, same line.
- **2024-25 single snapshot (no close):** profit per $1.
- Standard errors clustered by game.

## Find, then confirm

- **Discovery:** corners with 300+ bets; one-sided test that the mean is above 0; **Benjamini-Hochberg false discovery
  rate 10%** across every corner tested.
- **Confirmation:** a discovered corner must have mean above 0 with one-sided p < 0.05 on separate data, unchanged.
- Splits: 2024-25: discover on 2024-11-06 to 2024-12-31, confirm on 2025-01-01 to 2025-01-29. Live: discover on the
  first half of the collected game days, confirm on the second half (re-run as data accumulates; a corner is only
  "confirmed" on game days it wasn't discovered on). Past-morning data, if bought: discover on one season, confirm on
  the other.

Only confirmed corners are shown as bets on the site, with their measured edge and sample size. Stakes: a quarter of the
Kelly fraction at the confirmed edge, at most 1% of the bankroll per bet.

## Known limits

The 2024-25 single snapshot is an hour before tip, and profit needs many bets: expect little power there. Corners
overlap (the same bet sits in several), so confirmed corners can be redundant.

## Amendment (2026-10-21, before any live closing-line data existed)

The forward collection adds an **afternoon** snapshot (2:30-4 PM ET, after teams' game-day injury reports), so bets can
be placed at the morning or the afternoon snapshot. A **time** tag (morning / afternoon) joins the corner tags, so the
search also asks *when* any edge is. Everything else is unchanged.
