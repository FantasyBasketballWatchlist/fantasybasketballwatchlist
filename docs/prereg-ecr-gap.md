# Preregistration: where does the experts' preseason edge come from?

Written 2026-10-20, before any result was computed. Script: `analysis/ecr_gap.py` (results in `analysis/ecr_gap.json`).
Diagnostic only: nothing in the app changes because of it. It decides which missing information is worth chasing.

## Background

FantasyPros' preseason consensus (ECR) out-ranked the app's preseason blend at picking the season's best players in
4 of 4 seasons, even among veterans, but turned into points its season totals were *worse* (Round 10, item 2). So the
edge is in the **order** of players, and that's what this splits up.

## Data

Round 10's per-player frames (`analysis/round10.py: season_data`) for 2021-22 and 2023-24 to 2025-26: the app's
preseason blend as it stood in Round 10 (`base_total`), ECR rank, actual season FPTS total (0 if he didn't play).
Pool: the union of the blend's top 150, ESPN's top 150 and ECR's top 150; chosen before the season (no actual top 150,
which would select on the outcome).

## Measure

For every pair of players in a season's pool with different actual totals, each list gets 1 if it ordered them the
same way as the actual totals, 0 if not, 0.5 for a tie. A player missing from ECR counts as rank 300. Each pair's
difference (ECR minus blend) is split evenly between its two players, so a player's contribution is how much of ECR's
extra correct ordering involves him. Contributions add up to ECR's total edge.

## Groups (known before the season; each player in exactly one, first that applies)

1. **No NBA history** (rookies): no games last season or before.
2. **Injury / short season:** under 20 games last season, or ESPN projected under 60 games.
3. **Team changer:** on a new team since last season.
4. **Second year:** last season was his first.
5. **Settled veteran:** everyone else.

Also reported, overlapping: age 32+, age 23 or under, and pairs among each list's top 50 only.

## Output

For each group: players, contribution to ECR's edge (sum, per season, share of the total), per player. Then the
biggest single contributors with what the blend got wrong (games vs per game). No decision rule: the result says which
kind of information (roles, injuries, rookies) the edge comes from.

## Result (added after running it, 2026-10-20)

`analysis/ecr_gap.json`. Over all pool pairs ECR ordered 602 more pairs correctly than the blend (of ~57,000): 419 in
2021-22, 40 in 2023-24, 50 in 2024-25, 93 in 2025-26. Among each list's top 50 the blend ordered players better in
3 of 4 seasons (ECR much better in 2025-26). So the edge is smaller and more concentrated than the top-130 measure
suggested.

| Group | Players | Share of ECR's edge | Per player |
|---|---|---|---|
| Injury / short season | 24 | 33% | 8.2 |
| Settled veteran | 485 | 68% (2021-22 and 2025-26) | 0.8 |
| Team changer | 98 | 2% | 0.1 |
| Second year | 49 | 0% | 0.0 |
| No NBA history | 23 | -2% | -0.6 |

The largest single contributor was Tatum in 2025-26 (11% of the whole edge): ESPN had no projection for him and listed
him OUT; the blend ignored that and ranked him 6th; he played 16 games. Other veteran gains were availability news
(Kyrie Irving 2021-22) or role changes (Jordan Poole, Reggie Jackson, Mo Bamba). Rookies, team changers and second-year
players: no net edge.

Follow-up (a bug fix, not a preregistered test): ESPN's "out" signal (0 projected games, or no projection while listed
OUT) was being discarded. The 15 regulars it flagged in these seasons played 14 games on average; the app now uses
that (`ratings.ESPN_OUT_GAMES`). Small sample.
