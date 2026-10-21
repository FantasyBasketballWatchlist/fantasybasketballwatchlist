# Preregistration: the single-game projections against real sportsbook lines

Written 2026-10-21, before any line was downloaded. Code: `odds_lines.py` (download), `analysis/real_lines.py` (the
test; results in `analysis/real_lines.json`). The question: would betting on the projections' favourite side have
made money, at real prices?

## Data

- **Lines:** The Odds API, US sportsbooks (region `us`: DraftKings, FanDuel, BetMGM and others), player points,
  rebounds and assists, **2024-25** regular season from 2024-11-05 (the model needs 14 game days of the season first),
  one snapshot **an hour before each tip-off**, games in date order until 18,000 credits are spent (about 590 games).
  2024-25 is the season the fixes were tested on but never tuned on.
- **Projections:** the fixed model (`game_projections.FIX`) as in `analysis/game_fix.py` for 2024-25: only games
  before that day, fantasy-point anchor = season-to-date average shrunk toward last season (BPV isn't recomputed for
  past dates).
- **Players:** matched by name (accents, punctuation, suffixes ignored). Only player-games he played count (books
  void a prop if he doesn't play). Players who can't be matched are left out and counted.

## The bet

For each game, player and stat: the **line** offered by the most books (ties: the lower line); for each side, the
**median price** among books offering that line (a typical price, not the best one found by shopping). The model's
chance of each side at that line (whole-number lines: a push returns the stake). Expected profit per $1:
p(win) x (decimal odds - 1) - p(lose). A **bet** is the side with the higher expected profit, if it is above the
threshold. Every bet is $1.

## Measures and pass rule

- **Primary:** profit per $1 bet (ROI) for bets with expected profit **above 5%**, all three stats together, with a 95%
  bootstrap interval resampling game days.
- **Pass:** ROI above 0 with the interval's lower end above 0, **and** ROI above 0 in both halves of the sample (split at
  the median game date).
- **Secondary (reported, not part of the verdict):** ROI at thresholds 0%, 10% and 15%; ROI per stat; hit rate vs the
  break-even rate; calibration of the model's chances on real lines (5-point buckets); Brier score of the model vs the
  books' own no-vig chances (the two prices with the margin removed proportionally) on the same lines.

## If it fails

No betting rankings on the site; the Games page keeps its "information, not a betting edge" wording. If it passes, the
next step is a live record (daily lines, logged before tip-off) before anything is ranked as a bet.

## Known limits

- One snapshot an hour before tip-off: late news (a starter ruled out at tip) isn't in the line or in the projections.
- Prices are typical, not the best available, and limits/bet acceptance aren't modelled.
- ~590 games of one season; the interval says how much that matters.

Note (2026-10-21, before any result): a check of name matching on the first ~70 games found sportsbook spellings the
rule missed (A.J./AJ, nicknames such as Moe/Moritz Wagner); dots are now dropped and five nicknames are mapped
(`analysis/real_lines.py: ALIASES`). Only match counts were looked at.

Note (2026-10-21, after the first run): that run took the median of American odds, which isn't a price when books sit
either side of even money (-110 and +100 have a median near 0), so its profits were infinite and meaningless. Fixed by
taking the median in decimal odds, as "median price" intends; the bet rule is otherwise unchanged. The first run's hit
rates and calibration (which don't use the prices) were seen: 52.3% of the 5%+ picks won; the model was overconfident
on real lines (predicted 62% -> 53%, 72% -> 58%).

## Result (2026-10-21)

`analysis/real_lines.json` (results only; the raw lines stay on the PC). 592 games, 22,777 matched offers.
**Fails.** Bets with expected profit above 5%: 12,479 bets, ROI **-1.8%** (95% interval -3.5% to -0.2%), won 52.4% vs a
break-even of 53.4% at the median prices; -1.3% and -2.4% in the two halves. Every threshold loses (0%: -2.7%,
10%: -1.4%, 15%: -1.3%); points -3.5%, rebounds -1.7%, assists -0.1%. The books' no-vig chances are better than the
model's (Brier 0.247 vs 0.255), and the model is overconfident against real lines (62% predicted -> 53% won;
72% -> 58%). The projections beat a player's season average, but sportsbook lines already contain that and more.
No betting rankings; the Games page says it was tested against real lines and would have lost money.
