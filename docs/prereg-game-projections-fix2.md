# Preregistration: second round of single-game projection fixes

Written 2026-10-21, before any of these was computed. Code: `analysis/game_fix2.py` (results in
`analysis/game_fix2.json`). Motivation: the real-lines tests (`docs/prereg-real-lines.md`, `docs/prereg-real-lines-rules.md`)
and the research report (`reports/NBA player prop betting edge.md`) point to three fixable problems.

## Candidates (the only ones tried)

- **F1, shape:** points, rebounds, assists and points+rebounds+assists as a normal distribution with the variance
  x k (k in 1.0, 1.1, ..., 1.6), instead of the negative binomial, whose long right tail put its median below its mean
  and made it lean under against real lines.
- **F2, recent minutes:** the half-life H in {3, 5, 10, 20} games and weight w in {0.25, 0.5, 0.75} (now H = 3, w = 0.5,
  which over-reacted against real lines).
- **F3, teammate news** (from the official injury report of the game day, known before tip-off):
  - *new absences:* teammates listed Out or Doubtful who played in his team's previous game; *returns:* teammates with
    15+ minutes a game who missed the previous game and aren't listed Out or Doubtful;
  - net vacated minutes V = their minutes per game (last 10 games) over new absences minus returns;
  - his extra minutes = alpha x V x (his minutes per game / the minutes per game of the teammates expected to play);
  - his points and assists per minute x (1 + gamma x V / 240).
  - alpha in {0, 0.25, 0.5, 0.75, 1}, gamma in {0, 0.5, 1, 2}.
  Rebound and assist role transfer by position isn't possible without positions in the box scores; not tried.

## Choosing (design)

On **2025-26** box scores, the same way as the first fix round: per stat, the Brier score on proxy lines (the season
average rounded down + 0.5), in the order F1, F2, F3, each kept only if it lowers it. Everything else as in
`game_projections.FIX`.

## Test (once)

On the **2024-25 real sportsbook lines** (592 games, `data/lines/history.csv`), points, rebounds and assists:

1. **Primary:** Brier score of the fixed model's own chances (no market blend) vs the current model's, at the
   consensus line. **Pass:** lower for all three stats together.
2. Reported: Brier vs the books' no-vig consensus; the rule set's ROI (`analysis/real_lines_rules.py`) with the fixed
   model; error in games with teammate news.

Passing means the projections got closer to the books; it doesn't show an edge. That is judged only by closing-line
value on the forward snapshots (`analysis/clv.py`).

## Known limits

The 2024-25 lines were used to see the problems (and November-December to fit the blend weights): the test season
isn't untouched. The injury report's Out/Doubtful players are assumed not to play and unlisted ones to play.
