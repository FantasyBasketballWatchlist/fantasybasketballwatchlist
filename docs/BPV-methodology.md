# BPV: Measuring Fantasy Basketball Value

*Revised edition. Every number in this version comes from backtests on six NBA seasons (2019-20 to 2025-26) that you can re-run with `python -m analysis.backtest`. Appendix A lists what changed from the first draft and why.*

## 1. Fantasy value is not the same as basketball value

We used past NBA stats to predict fantasy basketball value. The bottom line: **fantasy basketball value is not the same as NBA basketball value.**

Imagine two players:

1. One is great at his job, always putting on a show and getting the crowd hyped, but he misses a lot of games. The fans may love him, but a fantasy manager doesn't get production worth the hype.
2. The other is slightly worse. He stays quiet and isn't promoted much on social media, but he consistently provides fantasy production and shows up to nearly every game. The fans wouldn't go crazy over him, but I would.

The best ability in fantasy basketball is availability, and fantasy managers get something real fans don't: when a player is out, they can put in someone else. Our goal isn't to find the best basketball player. It's to find which player gives a fantasy manager the most expected value.

## 2. Terms

- **ADP (average draft position):** Imagine 1,000 fantasy leagues drafting on the same night, each manager using their own evaluation. A player's ADP is the average pick at which he was taken. It describes where players *are* drafted, not where they *should* be.
- **BPV (Basketball Performance Value):** our adjusted score, in fantasy points per team game. Section 11 has the formula.
- **FPTS (fantasy points):** ESPN's scoring (Section 3).
- **Free agent:** a player nobody drafted, who any manager can add (subject to waivers if he was dropped recently).
- **Roster:** ESPN's standard league has 13 players: 10 starters (PG, SG, SF, PF, C, G, F and three UTIL) and 3 bench spots. Only starters' points count on a given day.
- **IR (injured reserve):** a slot that doesn't count against the 13. ESPN only lets a player go on IR if he has the O (Out), IR or IL tag. So a player listed Questionable or Day-to-Day can't go on IR. That rule is the whole reason Section 5 matters. The number of IR slots varies by league.
- **Waiver claim:** a recently dropped player goes through a waiting period, and managers who want him are queued by waiver priority. ESPN leagues can either reset priority weekly to reverse standings or move a manager to the back after each successful claim. The starting order in snake drafts is the reverse of draft order.
- **Replacement level:** what a typical free agent produces. In a 10-team league with 13-man rosters, 130 players are rostered, so the replacement player is roughly the 131st-best. In ESPN scoring he averages about **25–27 FPTS per game** (27.5 in 2025-26).

## 3. The scoring formula

ESPN's default points league scores:

> FPTS = PTS + REB + 2·AST + 4·STL + 4·BLK − 2·TO + 2·FGM − FGA + FTM − FTA + 3PM

This is a good base. It values points, rebounds and assists, and also efficiency: a made two is worth +3, a made three +5, a made free throw +1, and every miss −1.

We could redesign this around what I personally think matters most, but we can't drift from the real scoring system:

- Points are points. We can't decide assists should be worth +3 instead of +2 because we think assists are undervalued.
- We aren't saying "this is what the scoring system should be." We're saying "given the current scoring system, this is our adjusted method of valuing players."

**BPV always works in FPTS per game.** Season totals already include games played, and multiplying a total by an availability percentage would count missed games twice.

## 4. Availability, and why simple multiplication is too harsh

Two players:

- **Player A** averages 45 FPTS and plays 60% of games: 45 × 0.60 = 27
- **Player B** averages 30 FPTS and plays 90% of games: 30 × 0.90 = 27

I'll admit I get fixated on the bigger average at first, but after availability they look identical. They aren't, because a missed game isn't worth zero. When Player A is OUT, you can put him on IR and pick up a free agent for as long as he's out. If a free agent gives you about 20 FPTS on those days:

- **Player A:** 45 × 0.60 + 20 × 0.40 = 35
- **Player B:** 30 × 0.90 + 20 × 0.10 = 29

As one formula, with *F* = FPTS per game played, *p* = share of games played and *R* = replacement level:

> **Value = p·F + (1 − p)·R = R + p·(F − R)**

Plain multiplication is the special case R = 0: it assumes you get nothing at all when a player sits. The second form shows what actually matters: how far a player is above a free agent, times how often he's there.

There are two limits on replacing an injured player:

- A standard league has only one or two IR slots. If someone is already there, the next injured player's missed games really are worth zero.
- The bench is different from IR. Benching a player means choosing not to count him that day. It doesn't open a roster spot.

## 5. Different kinds of missed games

**Player D** misses 30 straight games with an injury. **Player E** misses 30 games scattered across the season. Their availability is identical, but in fantasy they are very different:

- Player D goes on IR once, and you stream free agents in his spot until he returns.
- Player E cycles "Questionable → Out → Questionable." He can't go on IR while Questionable, and if he's ruled out late you miss your chance at a waiver pickup or have to make an awkward bench decision.

So only the *long* absences get the free-agent credit:

> **BPV = p·F + (1 − p)·q·R**

Here **q** is the share of missed games that come in stretches of 5 or more straight team games. We measure it from game logs by comparing each player's games to his team's schedule (Appendix B).

**What the data says:**

- Across the league, about **72%** of games missed by regular rotation players (20+ minutes a game) come in long stretches.
- A player's own q barely carries over from one season to the next: the correlation is only about **0.09–0.13**, depending on how "long" is defined, across roughly 870 player pairs.
- **That does *not* prove erratic absence isn't a trait.** One season's q is too noisy to measure anything. Even the *first half* and *second half* of the same season correlate at only about 0.07, which puts the reliability of a full season's q at about 0.12. Correcting the year-to-year correlation for that noise would put it anywhere from about 0.4 to 0.75, but that correction is itself very uncertain. The honest summary is **"we can't tell from box-score data."** Part of the noise is that game logs can't separate injuries from rest days, suspensions or coach's decisions.
- So BPV uses the **league-average q for everyone.** A measurement this unreliable should be almost entirely replaced by the average. The Player D vs. Player E intuition is still plausible; we just can't measure it per player yet. Injury-report data (Section 17) would be the way to test it. When you know a player is out for a long stretch right now, enter it manually (Section 8). That long absence then gets the free-agent credit.

## 6. Keep availability visible

Combining production and availability into one number hides information, so the site shows both separately:

| | Production (FPTS/game) | Availability | BPV |
|---|---|---|---|
| Player A | 45 | 60% | 35 with R = 20 |
| Player B | 30 | 90% | 29 with R = 20 |

A manager with a full IR slot or no bench depth should lean toward Player B. The formula above is our default way to combine the two numbers into one ranking.

## 7. Estimating availability from history

The first draft used **career games played %**. We tested four ways to predict a regular's availability next season, on 2021-22 through 2025-26:

| Method | Average error (share of games) |
|---|---|
| Last season only | 0.187 |
| Career GP% (first draft) | 0.172 |
| Give everyone the league average (about 74–75%) | 0.174 |
| **Recent seasons weighted, shrunk toward the league average** | **0.166** |

To avoid tuning on the answers, each season's settings here were chosen using only earlier seasons (953 player-seasons in all).

- Career GP% was **not significantly better than assuming every player is average**: the 95% interval for the difference runs from −0.011 to +0.006.
- The shrunk estimate *is* better (−0.013 to −0.004), but only by about **one percentage point of games**.
- Availability is mostly unpredictable: this season's and next season's availability correlate at only **0.24**.

The best method weights each season half as much as the one after it, then blends in **123 games of league-average availability**. That's about a season and a half, so a player's own record needs more than that before it outweighs the league average. The result is that availability separates players by a few percentage points, not by 30.

The formula (Appendix B) is `p = (n·own + 123·league) / (n + 123)`, where *n* is the player's recency-weighted games.

This also fixes several problems with career GP%:

- The 2011-12, 2019-20 and 2020-21 seasons had 66, 64–75 and 72 games, not 82. We count real team schedules.
- Traded players appear as several rows plus a total row in the NBA's career table, which double-counted their games. We work from game logs instead.
- A player who missed an entire season (for example a torn Achilles) doesn't appear in that season's stats at all. We count that season as fully missed.

**Can we tell who is injury-prone beyond this?** We tested 23 possible warning signs against both the history estimate and ESPN's projected games (1,203 player-seasons, 2021-22 to 2025-26, each scored on seasons it wasn't fitted on, by average and by squared error): age (straight line and 32+), minutes per game, total minutes, playoff minutes, past serious injuries and specific body parts (knee, back, foot/ankle/Achilles, hamstring/calf), games missed at the end of last season or in its second half, the number of separate absences, the share in long stretches, the trend from two seasons ago, weight, height, weight per inch, usage rate, team record, years in the league, injury vs rest absences, and all of them together. **None helped**; several made things worse, and all of them together was clearly worse (overfitting). The current estimate only moderately identifies who will lose a season (under 50% of games): in about 61–65% of pairs, it rates the player who lost the season lower (50% = coin flip), and no factor meaningfully improved that. Before the season, ESPN's projected games beat the history estimate (average error 0.161 vs 0.164 on the same players), which is why the app uses them.

**During the season, one sign does help: a current absence.** A regular (20+ minutes per game) who isn't listed Out with an injury but has missed his team's last few games plays less of the rest of the season than his record suggests: about 2.4 percentage points less per game missed, up to 20. The residual grows steadily: +0.01 with no current absence, −0.09 after one missed game, −0.18 after four, −0.36 after twelve or more. On 10,139 in-season checkpoints this beat the current estimate in 4 of 5 seasons by average error (−0.0034, interval −0.0049 to −0.0023) and 5 of 5 by squared error, with the same slope in every season. For currently absent players, error fell about 0.02. **BPV now applies it in season**, when the team has 10+ games left (the test stopped 3 weeks before each season's end, when teams start resting players). Not added: counting this season's absences more heavily (better by average error, not by squared error, which is what matters for an expected value), age, the latest report status (Probable/Questionable/Doubtful), non-injury Out listings, and having just returned from a long absence.

## 8. Injury risk and the Cox model (built and tested)

I tested several formulas and realized I wasn't as well equipped as people whose job is this calculation. Aryan Jha's article *"Figuring out why NBA players get injured using Cox Proportional Hazards"* (Medium, September 28, 2025) is a useful reference:

- **Data:** every All-Star since 2005-06: 120 players, 1,420 player-seasons and 70 season-ending injuries. Injuries came from a Kaggle dataset and stats from `nba_api`.
- **Event:** a season-ending injury. Time is measured in games into the season.
- **Significant factors:** height, season, field goals made, rebounds, blocks, fouls committed, fouls drawn and points.
  - Each extra inch of height carried about a **31% higher hazard**.
  - A 6'3" player had about a 98.7% chance of finishing 82 games without a season-ending injury, vs. 89.4% for a 6'11" player.

**How the Cox model works.** The model is `h(t|x) = h₀(t)·e^(β₁x₁ + … + βₚxₚ)`. It doesn't match a player to similar historical players. It fits one weight β per trait across all players at once. The output `e^(βx)` is a **relative risk**: above 1 means *riskier*. Multiplying FPTS by it directly would therefore *raise* risky players' values.

**The correct way to use it:**

1. Convert the relative risk into a probability of staying healthy: `S(t|x) = S₀(t)^e^(βx)`.
2. Or, following our percentile idea, rank players by risk, group them into percentile buckets, and use each bucket's **historically observed** games-played share as its availability (Appendix C shows the procedure).
3. Plug that availability into p in Section 5. Don't multiply by the percentile itself: a raw percentile would give the riskiest player about ×0.05, and it ignores how big the gaps between players actually are.

**Limits:**
- The article models only *season-ending* injuries in All-Stars. It says nothing about the short, frequent absences in Section 5.
- Minutes and points are inputs, so the model can partly penalize production itself.
- The article text reports no out-of-sample accuracy (such as a concordance index).

**We built and tested a Cox model anyway, without injury reports.** Box scores already record what hurts a fantasy manager: absences. The model predicted *when a player's first long absence of the season would start* (10+ straight missed team games, whatever the cause), using height, weight, age, last season's minutes, usage, games played and production, BPV's availability estimate, and his history of long absences. Each season from 2022-23 to 2025-26 was predicted with a model fitted only on earlier seasons, and the risk scores were turned into availability through percentile buckets (Appendix C).

| | Cox model | BPV's current estimate |
|---|---|---|
| Ranking of who misses time (C-index; 0.5 = random) | 0.53–0.60 | 0.56–0.61 |
| Availability error, Cox alone vs current | +0.004 (worse; interval +0.000 to +0.007) | — |
| Cox added on top of the current estimate | +0.0002 (tie; interval −0.0006 to +0.0009) | — |

The result was the same with long absences defined as 5+ or 20+ games. Height was the only factor with a hint of signal (about 11% more risk per standard deviation, p = 0.08), in the same direction as Jha's finding. **Verdict: the Cox model doesn't beat BPV's current availability estimate, so it isn't used.**

**Official injury reports (2021-22 on).** We then added the NBA's official injury reports: one per game day, 816 days, about 60,000 player listings, read with the `nbainjuries` package. They give a status and a reason for every listed player, which box scores can't.

- **Why regulars (20+ mpg) miss games:** injury 81%, rest 6%, G League 4.5%, COVID protocols 3.6% (16% in 2021-22), personal 2%, suspension 1%. **Rest has grown from 2.6% of absences in 2021-22 to 9.3% in 2025-26**, even after the 2023 Player Participation Policy limited star rest.
- **Status → played:** Probable 91%, **Questionable 49%**, Doubtful 1.7%, Out 0.2%.
- **Serious injuries identify long absences with no hindsight.** A 20+ mpg player listed Out with a serious injury (surgery, tear, fracture, rupture, ACL, Achilles, meniscus...) played a median **7%** of his team's remaining games. For those players, BPV's usual availability estimate was off by 0.60; the report-based estimate is off by 0.16 (interval for the gain 0.18–0.60). A teammate boost triggered by such listings beat current BPV (−0.25 FPTS/game for affected players, interval −0.40 to −0.11; coefficient 0.029 per lost minute). An "Out" listing *without* a serious reason didn't help (tie). **So in season, BPV now reads the latest report automatically** and treats serious injuries as long absences.
- **Injury and rest history don't improve next season's availability** (tie: −0.0004, interval −0.0014 to +0.0005), and resting is only a weak habit (year-to-year correlation 0.20; regulars average under one rest game a season).
- The Player D vs. E question (Section 5) still can't be settled: the reports cover five seasons, too few player pairs to overcome the noise in one season's pattern.

**Manual injury input.** Until then, known injuries go in `data/overrides.json`, for example `"Player Name": {"out_for_season": true}` or `{"out_games": 10}`. Those games are treated as one long, IR-able absence.

## 9. Buy low, sell high

No NBA player produces the same numbers every night, and some swing more than others. When a player is on a really good or bad run, you can take advantage.

**1. Sell high.** When a player gets hot, it's easy to believe he may be the next big thing. More often than not, he isn't. Say your player has been doing well lately, but you don't know how long it will last, and your friend has a player who looks mediocre right now but has been consistent in past seasons. Trade the hot player for the consistent one. Your friend wins in the short run, and you win in the long run.

**2. Buy low.** Have you ever drafted a player and been bummed when he underperformed for a few weeks right when you needed him? It's happened to me plenty. I've given up on players like that, then realized later they were as good as I'd thought and I'd acted too impulsively. If someone wants to get rid of an underperformer, you can trade something that looks better right now for him, knowing it will be worth it by the end of the season.

**The data now tells us which streaks to trust.** Splitting a player's last-5-games change into the part from **more or fewer minutes** and the part from **per-minute production** (shooting and luck):

- About **30%** of a minutes change carries through the rest of the season.
- Only about **10%** of a per-minute change does.
- Minutes are nearly a coach's decision and stabilize within about 1.5 games (Medvedovsky, 2020). Shooting percentages take hundreds of attempts.
- So a player who is hot **in the same minutes** is the sell-high candidate, and a player whose **minutes jumped** is the real pickup. The Waiver Wire page sorts players into exactly these groups.

Why not just maximize short-term wins? Two words: **fantasy playoffs.** At the end of the season you compete head to head in a bracket for the championship, and that's when your team needs to be at its best.

**Example.** My player L had a hot week but has never been that good. My friend's player M was a 2nd-round pick playing like a 5th-rounder over the past week, and my friend offered M for L. I was skeptical but still believed in M, so I checked BPV: L at 23.0 and M at 25.2. I took the deal with confidence. BPV discounts L's streak and keeps most of M's longer track record.

## 10. Recent form: the 80/20 rule, tested

The first draft proposed **BPV = 80% season performance + 20% last 5 games**, with "season performance" meaning the current season only.

**Which 5 games.** The first draft said that if a player missed 3 of the last 5 team games, the 2 he played would count as the recent 20%. We tested that version (the team's last 5 games, averaging only the ones he played) against simply using his **last 5 games played**. The last 5 games played predicted slightly better, and it avoids basing "recent form" on 1 or 2 games. BPV uses the last 5 games played, and absences are handled by availability, not by recent form. Early in the season, with fewer than 5 games, BPV uses the season average alone.

**Why 5 games.** NBA teams play about **3.4 games a week** on average (82 games over roughly 24 weeks), so 5 games is about a week and a half. That's enough to mean more than one good game.

**Why 20%.** At every weekly checkpoint in 2021-22 through 2024-25 (21,427 player-checkpoints), we predicted each player's rest-of-season FPTS per game with every weight from 0% to 60%. We then checked the result on 2025-26 (5,404 checkpoints), a season the weights never saw:

| Recent weight | 0% | 10% | 15% | 20% | 30% | 50% |
|---|---|---|---|---|---|---|
| Average error, FPTS/game | 4.26 | 4.21 | **4.20** | 4.21 | 4.26 | 4.50 |

- **Some recent weight clearly helps.** On 2025-26, 20% beat 0% by 0.11 FPTS per game (95% interval 0.05–0.17), about 3% less error.
- **The exact weight can't be pinned down.** Resampling players, the best weight was 15% in 88% of resamples, and the interval covers 10% to 20%. The best weight in individual seasons was 20%, 10%, 15%, 10% and 20%. On the unseen season, 20% and 15% are statistically tied (difference 0.008, interval −0.024 to +0.005). **20% is a reasonable choice inside the supported range, not a confirmed optimum.** For the next two weeks only (start/sit decisions), 20–25% did best.
- **The minutes/efficiency split from Section 9** is solid as a finding: the minutes weight (0.29, interval 0.25–0.34) is clearly above the efficiency weight (0.09, interval 0.07–0.12). As a *prediction* improvement over plain 80/20, though, it's small and not statistically significant (0.02 FPTS per game, interval −0.044 to +0.002). **BPV uses the split** (season FPTS + 0.3 × minutes change + 0.1 × per-minute change) because it's at least as accurate and matches the research on how quickly stats stabilize. Plain 80/20 would be almost as good.
- The weighting counts recent games twice, because the last 5 are also part of the season average. At game 50 their real weight is 0.2 + 0.8 × 5/50 = 28%. The backtest accounts for this automatically.

**Offseason and preseason.** Last season's final 5 games are a poor guide to next season, because contenders rest stars and lottery teams play their bench. In preseason tests, the 80/20 version predicted the next season no better than the plain season average. So BPV turns recent form off between seasons.

## 11. New roles

Player N has played all of the first 50 games as a bench player at 10 minutes a game. Then the starter gets injured, and N starts playing 30 minutes a game. His production should skyrocket, but those first 50 games don't know about his new opportunity.

> **New Role Value = FPTS per minute × new minutes per game × 0.90**
>
> **BPV = 40% × previous value + 60% × New Role Value**

**Why 90%:** we can't assume someone's per-minute production at 10 minutes a game carries straight over to 30. More minutes can mean more fatigue, different usage and different on-court opportunities.

We tested this on every case where a player's last-5 minutes rose at least 8 above his season average (from 24 minutes or less), 703 cases in all:

| Method (on 2025-26, unseen) | Error, FPTS/game |
|---|---|
| Season average only | 7.85 |
| 80/20 recent form | 6.36 |
| **New Role Value, 90%, 50/50 (first draft)** | **5.36** |
| New Role Value, 90%, 60/40 (fitted) | 5.24 |

**The idea is strongly supported; the exact numbers aren't.**
- New Role Value beat 80/20 on the unseen season by about **1.0 FPTS per game** (95% interval 0.5–1.4), and it cut error by a third compared with the season average.
- The best fit on the tuning seasons was a 0.90 haircut with 60% weight, but many pairs fit within 1% of it. For example, **no haircut (1.00) with 40% weight** fits just as well, because the haircut and the weight trade off against each other.
- Resampling players, the best haircut ranged from 0.80 to 1.10 and landed on 0.90 only 23% of the time.
- So the data doesn't confirm the fatigue reasoning behind 90%; it can't tell 0.8 from 1.1. BPV keeps 0.90 with 60/40, the best single fit, and any nearby pair is equally defensible.

**Detection.** The site detects role changes automatically when a player's last-5 minutes are 8 or more above his season average, he averaged 24 minutes or less, and he has played at least 10 games. It isn't applied to everyone, only to a clear role shift. An algorithm can't tell whether the starter is out for a week or for the season, so you can also mark a role change by hand with a start date in `data/overrides.json`.

## 12. Players without much history

**Early in the season.** Five games tell you little, so BPV blends a returning player's current production with **8 games' worth of last season's level**. This was the best value in backtests: it cut early-season error from 5.1 to 4.1 FPTS per game. By about game 24, the current season carries 75% of the weight. Last season's level is **age-adjusted** first (Section 13); that cut early-season error a further 0.05 FPTS per game (95% interval 0.02–0.08) on 11,587 checkpoints. For players who got the preseason BPV + ESPN blend (Section 13), that **preseason projection** replaces last season as the prior: −0.064 FPTS/game (95% interval −0.102 to −0.025), better in 3 of 4 seasons (2025-26 was a tie), 7,654 checkpoints; no significant change for the top 10% of players. The app saves each preseason's projection to `data/preseason/` so it can be used once the season starts; ESPN's in-season projections (rest of season) are never used.

**Rookies** have no last season, so BPV starts from the average rookie season of players drafted in the same range (drafts 2020–2025):

| Pick | Rookie FPTS/game | Minutes/game | FPTS per minute |
|---|---|---|---|
| 1–3 | 31.0 | 29.3 | 1.05 |
| 4–10 | 18.2 | 21.4 | 0.85 |
| 11–20 | 15.6 | 18.3 | 0.86 |
| 21–30 | 12.0 | 15.1 | 0.81 |
| 31–60 | 8.8 | 11.2 | 0.80 |
| Undrafted | 8.2 | 11.0 | 0.81 |

A rookie's real games are blended with **10 games** of that baseline, which was the best value in backtests.

**Players who haven't played an NBA game yet** (newly drafted rookies) get the baseline for their pick range, availability at the league average, and a *"projection only"* label. The first version gave them 0. Since 2026-10-17, before the season, rookies ESPN projects are blended 37.5% with ESPN's per-game projection and take their games from ESPN (× 0.86), the same rule as veterans; see the rookie test below.

**Players who missed all of last season** (e.g. a torn Achilles) but are on a roster and played 20+ games the season before start from that season's FPTS per game, with the age adjustment and the usual ESPN blend and games before a season. Before 2026-10-17 they were left out of the rankings entirely (Haliburton, Lillard, Irving and VanVleet for 2026-27). This path has not been backtested.

## 13. Between seasons: age and roster competition matter, older seasons don't

Before a season, BPV has to project each player's production from what he did before. We compared six ways of doing that on 1,151 player-seasons (players with 20+ games in both seasons and 15+ minutes per game). Each target season (2022-23 to 2025-26) was predicted with settings tuned only on the other three.

| Preseason production model | Error, FPTS/game |
|---|---|
| Last season's FPTS per game (BPV before this test) | 4.61 |
| Last three seasons blended, shrunk toward the average | 4.61 (tuning chose last season only) |
| Last three seasons of *per-minute* production × last season's minutes | 4.67 (significantly worse) |
| Basketball-Reference's Simple Projection System (6/3/1 blend, regression, age adjustment) | 4.56 |
| **Last season + age adjustment** | **4.40** |

**Age is the real signal.** Average change in FPTS per game from one season to the next, by age during the season just played:

| Age | ≤21 | 22–23 | 24–26 | 27–29 | 30–32 | 33+ |
|---|---|---|---|---|---|---|
| Change | +2.1 | +0.3 | −0.3 | −1.6 | −2.5 | −3.7 |

- The age adjustment cut error **4.7%** (0.22 FPTS per game, 95% interval 0.12–0.31) and helped in **all four** seasons.
- It **beat Basketball-Reference's projection system** by 0.16 FPTS per game (interval 0.04–0.27).
- A flat adjustment (the same number of points for everyone that age) beat a proportional one (the same percentage), especially for stars.
- The curve is stable over time: fitted only on seasons before 2022-23 it looks nearly the same as the one fitted on all four seasons.
- **Caveat:** players who fell out of the league were excluded, which probably *understates* the decline at older ages.

**Older seasons add nothing,** tested two ways. That goes against standard practice in other projection systems (Basketball-Reference and baseball's Marcel blend three seasons). A likely reason: a fantasy player's value is mostly his current role and minutes, and older seasons describe roles he no longer has. We also tested replacing the last-5 rule with exponential decay (every game counting a little less than the next). It tied the current method, so recent-form weighting has hit its ceiling.

**Next season's roster matters too.** Using next season's rosters (public before the season), we measured each player's *crowding*: the total last-season minutes per game of his new teammates who played 10+ minutes, minus the league-average team. More crowding means fewer minutes to go around.

- Crowding cut preseason error by a further 0.06 FPTS per game (interval 0.02–0.10), with the same coefficient in all four held-out seasons: **−0.018 FPTS per game per minute of crowding.** Joining a team with 40 more rotation minutes than average costs about 0.7 FPTS per game.
- Simply knowing he *changed teams* did not help (−0.02, interval −0.04 to +0.003), and adding it on top of crowding made things worse. What matters is the competition for minutes, not the move itself.
- Preseason rosters list about 20 players per team versus about 15 on opening night, but only players who averaged 10+ minutes count, so the crowding scale is close to the tested one (spread 37 vs 26–33).

BPV now uses **last season + age adjustment + crowding** between seasons, for players with 20+ games and 15+ minutes per game, then blends in ESPN's preseason projection (below). Rookies with 2+ preseason games also get +0.31 FPTS/game for each preseason minute per game above the typical rookie from their draft range (tested: −0.21 FPTS/game error). Veterans' preseason minutes didn't help (stars rest in preseason; increases carry over, decreases don't).

**Head to head with ESPN.** ESPN's public fantasy API still serves its preseason projections for past seasons (2021-22 and 2023-24 to 2025-26 are genuine preseason numbers; its 2022-23 file was frozen mid-season, so that season is excluded). This is the competitor comparison the paper had been missing:

| Preseason projection (everyone who qualified the season before; 0 if they then missed the season) | Error on season totals | Ranking accuracy (rank correlation with actual totals) | Simulated drafts (avg team FPTS) |
|---|---|---|---|
| ESPN | 576 | 0.671 | 27,470 (won 1 of 4) |
| BPV alone | **502** | 0.664 | 26,510 (won 0) |
| **BPV + ESPN hybrid** | **496** | **0.686** | **28,520 (won 3 of 4)** |

- **Per game, BPV beats ESPN** (4.36 vs 4.55 FPTS/game error; ESPN over-projects by about 1.6). But a **blend beats both**: roughly 62.5% BPV, 37.5% ESPN.
- **ESPN's projected games carry information BPV lacks** (preseason injuries, suspensions and holdouts): with them, ESPN out-ranked plain BPV on season totals and in drafts. But ESPN projects too many games (median 66–72), which hurts its totals.
- **The hybrid** uses the per-game blend with ESPN's projected games scaled by 0.86. It ties BPV on total error, beats ESPN by 80 FPTS, ranks players significantly better than ESPN (+0.016, interval +0.007 to +0.024) and won 3 of 4 draft seasons. **BPV now uses this hybrid before each season** for players with 20+ games and 15+ minutes the season before. It isn't used in season, where ESPN switches to rest-of-season projections that we haven't tested.
- **Honest summary:** plain BPV was *not* the best preseason ranking; ESPN was. The hybrid is the best of the three we can test. The earlier "BPV beat the experts" experiment (Section 14) should be read in that light.

## 14. The experiments

Before the 2025-26 season we compared five sources: ESPN projections, ADP, my personal rankings, BPV, and professional analysts.

**Experiment 1:** each source drafts its ideal 13 players, as if it were the only manager.

1. ESPN: 43,565 FPTS
2. BPV: 43,113 FPTS
3. Professionals: 41,851 FPTS
4. My rankings: 41,119 FPTS
5. ADP: 40,904 FPTS

**Experiment 2:** all five compete in one draft with a randomly assigned order, like a real league.

1. BPV: 39,096 FPTS
2. My rankings: 38,058 FPTS
3. ESPN: 37,420 FPTS
4. ADP: 32,752 FPTS
5. Professionals: 27,891 FPTS

**We can't simply say "BPV beat the experts."**

- **Randomness.** Anyone can make a good call on a player who then gets hurt. Experiment 1 is essentially a tie (a 1% gap), and Experiment 2 is one draft, where draft position alone can swing the result by thousands of points.
- **The draft itself.** Imagine someone had almost every projection right. Surely that list wins? Not necessarily. You don't know who will be left at your turn, so the best list doesn't guarantee the best team.
- **What BPV was at the time.** If the preseason rankings came from the first version of the site, they were season FPTS × career GP%, plus a hand-made list of 40 players set to 0. That list covered 2024-25 injuries, not all of which carried into 2025-26. Its preseason "last 5 games" were also the end of 2024-25 (Section 10).
- **Totals overstate.** Summing all 13 players' season totals ignores that only 10 can play each day, and that leagues are decided by head-to-head playoffs.

**Doing it properly.** Instead of one draft, we simulated **1,000 drafts per season**: 10 teams, 13 rounds, snake order, and each source getting 2 randomly placed seats. Every team drafts the best player left on its list. We ran this for four seasons (each predicted from the season before) and also measured each source's **rank correlation** with actual results.

Teams are scored by **actual season FPTS**. Each season's BPV settings were tuned only on earlier seasons, so no model sees the season it's scored on.

| Preseason model | Rank correlation with actual FPTS | Draft sim (avg team FPTS) | Draft-sim wins |
|---|---|---|---|
| Last season's total FPTS (like a naive consensus) | 0.638 | 26,740 | 0 of 4 |
| Model 1: season FPTS/game | 0.644 | not simulated | — |
| Model 3: × career GP% (first-draft BPV) | 0.651 | 27,050 | 0 of 4 |
| Model 5: 80/20 × career GP% | 0.654 | 27,850 | 0 of 4 |
| Revised BPV (Section 5) | 0.651 | 28,510 | 2 of 4 |
| **Revised BPV + age (Section 13)** | **0.665** | **28,520** | **2 of 4** |

These are averages over 2022-23 to 2025-26. BPV here uses the league-average q, as the site does, and each season's age curve was fitted only on earlier seasons.

**How to read this honestly:**
- **Ranking:** BPV + age has the best average rank correlation. It is significantly better than BPV without age in 2 of 4 seasons and tied in the others. Against Model 5 it's significantly better only in 2022-23.
- **Drafts:** a BPV version (with or without age) finished first in **all four** seasons, and the two versions split the wins. The age curve didn't add anything in drafts. Four seasons is still a small sample, and the simulations shuffle draft order but can't replay the seasons.
- **The conclusion we can defend:** BPV + age is at least as good as every alternative and best on average. The evidence that it's *better* is growing but not conclusive.
- We previously also reported a "managed" score that credited free-agent points for long absences. We've dropped it from the evidence because it **builds in BPV's own assumption**, so of course BPV scored well on it.
- One small look-ahead remains: players who never played again after the season being predicted (mostly retirements) are left out, since a preseason ranker would know about retirements.

To rerun Experiments 1 and 2 properly with ESPN, ADP, professional and personal lists, save each ranking as a CSV of player names and use `analysis/draft_sim.py`.

## 15. Models we compared

The first draft listed nine candidate models. Several needed fixing before they could be tested:

- **"Season FPTS" must be per game.** Otherwise availability is counted twice (Section 3).
- **Models 4, 6 and 9 multiplied by a Cox hazard ratio,** which rewards risky players (Section 8). They need an expected availability instead, and that needs injury data we don't have yet.
- **Models 7–9 applied New Role Value to everyone.** For a player whose role didn't change, it quietly cut his value 5% and halved the recent-form weight. New Role Value now applies only to detected or manually marked role changes.
- **Our strongest idea (Section 4's replacement-level formula) wasn't in the list.** It is now the core of BPV.

**The final model:**

> **BPV = p·F + (1 − p)·q·R**

- **F** = FPTS per game: season + 0.3 × minutes change + 0.1 × per-minute change over the last 5 games, or New Role Value for role changes. Early in the season it's blended (8 games) with the saved preseason projection, or with last season when there is none, or with a draft-slot baseline (10 games) for rookies. Between seasons it's last season plus the age and roster-crowding adjustments, blended 37.5% with ESPN's preseason projection (Section 13). In season it's recalibrated (actual ≈ 2.96 + 0.91 × projection), and hot or cold shooting is regressed toward the player's own level (−1.85 × eFG% difference × FGA per game).
- **p** = expected availability: recent seasons weighted, shrunk toward the league average (123 games). Before a season, ESPN's projected games × 0.86 / 82 where available; in season, adjusted for injuries on the official report by injury type.
- **q** = share of misses that are IR-able long stretches (league average, about 72%).
- **R** = replacement level (the 130th-best FPTS per game).

The **Heat Check Index** is BPV as a percentage of the league's best BPV.

## 16. Every improvement we tested

Candidates came from our own ideas and two rounds of research into published projection systems (DARKO, EPM, FiveThirtyEight, Basketball-Reference, SCHOENE) and peer-reviewed work. Public, out-of-sample evidence on season-long fantasy projections turned out to be scarce; most "fantasy edge" content has no numbers behind it.

**Three findings from the second round deserve a note.**
- **BPV was slightly too extreme in season.** Low projections came in about 2.4 FPTS/game low and high ones about 0.4 high, mostly because young players (under 24) improve during a season (+1.9 to +2.7 FPTS/game) and older ones fade slightly. About a third of the gap is a selection effect: only players who kept playing can be scored. A simple recalibration fixes most of it.
- **Tanking is real and large.** On bad teams (35% wins or fewer two weeks before the fantasy playoffs), young regulars play 24 percentage points less of their games in the final four weeks than earlier in the season, and veterans 28+ play 44 points less; on other teams the drop is about 8–10 points. Top teams show no such effect. Their young players' production per game rises 14% when they do play.
- **Per-stat stabilization matches Medvedovsky's pattern** (turnovers and shooting settle slowest, points and assists fastest) but doesn't beat BPV's single blend.

Rule set before testing: a change is added only if it beats current BPV on seasons it wasn't fitted on, with a 95% interval (resampling whole players) that excludes zero. Features that don't predict anything are added only if they're correct and harmless.

| Candidate | Result vs current BPV | Decision |
|---|---|---|
| Age adjustment between seasons | −0.21 FPTS/game (−0.31 to −0.12) | **Added** |
| Roster crowding between seasons | −0.06 (−0.10 to −0.02) | **Added** |
| Age-adjusted early-season blend | −0.05 (−0.08 to −0.02) | **Added** |
| Known long-term teammate absence, in season | −0.52 for affected players (−0.79 to −0.24) | **Added** (manual injuries only) |
| Same, guessed from missed games (no hindsight) | +0.00 (−0.03 to +0.03) | Not added |
| Teammate out for one game (game-level) | −0.10 per game (−0.14 to −0.06) | Not added: needs a live injury feed; BPV values the rest of the season |
| Cox injury model | +0.004 alone; +0.0002 combined | Not added |
| Averaging with Basketball-Reference's projections | −0.03 (−0.06 to +0.01) | Not added (tie) |
| Blending older seasons (two ways) | +0.00 / +0.05 (worse) | Not added |
| Exponential decay instead of last 5 games | −0.01 (−0.05 to +0.02) | Not added (tie) |
| Last 3, 7, 10 or 15 games instead of 5 | all within ±0.02 | Not added (tie) |
| Separate recency weight per stat | +0.03 (+0.00 to +0.05), worse | Not added |
| Separate age curve per stat | identical (additive) or +0.03 (proportional) | Not added |
| Proportional age adjustment | +0.03 (−0.01 to +0.07) | Not added |
| Changed-team flag | −0.02 (−0.04 to +0.00) | Not added (tie) |
| Positional replacement levels | under 0.3 FPTS/game from overall; draft sims +1.4% (−3% to +4%) | Not added |
| 80% likely range | covers 79.8% in season (target 80%); 72–82% between seasons | **Added** (display) |
| Fantasy-playoff game counts | −0.8% error on playoff-window totals (−1.7% to −0.04%) | **Added** (display and tiebreaker) |
| League size and roster size as settings | changes replacement level | **Added** (defaults 10 teams, 13 players) |
| Serious injury on the official report → long absence (own availability) | error 0.60 → 0.16 | **Added** (automatic, in season) |
| Teammate boost from serious-injury listings (no hindsight) | −0.25 for affected players (−0.40 to −0.11) | **Added** (automatic, in season) |
| Teammate boost from any "Out" listing | −0.02 (−0.11 to +0.06) | Not added (tie) |
| Last season's injury and rest absences → next season's availability | −0.0004 (−0.0014 to +0.0005) | Not added (tie) |
| Status → chance of playing (Probable 91%, Questionable 49%, Doubtful 2%) | measured on 60,000 listings | **Added** (display) |
| Recalibration of in-season projections (actual ≈ 2.96 + 0.91 × projection) | −0.07 pooled (−0.12 to −0.02); better in 3 of 5 seasons, never worse | **Added** |
| In-season age drift instead of recalibration | −0.06 (−0.16 to +0.04) | Not added (tie) |
| Per-stat stabilization padding (Medvedovsky) | −0.01 (−0.08 to +0.06) | Not added (tie) |
| Lighter early-season shrinkage for stars | +0.00 (−0.01 to +0.01) | Not added (tie) |
| Late-season tanking/resting in the fantasy playoffs | −2.8 FPTS per playoff-window total (−4.5 to −1.2); better in all 5 seasons | **Added** (expected playoff FPTS) |
| Rookie draft age | −0.02 (−0.07 to +0.04) | Not added (tie) |
| Usage-weighted teammate boost | +0.08 (−0.00 to +0.17) | Not added (tie, leaning worse) |
| Contract-year effects | not tested (no free contract data; published evidence mixed) | — |
| **BPV + ESPN hybrid before the season** (Section 13) | ranking +0.016 vs ESPN (+0.007 to +0.024); total error −80 vs ESPN, tie vs BPV; drafts 3 of 4 | **Added** |
| ESPN projections alone | total error +74 vs BPV; per game +0.19 vs BPV | Not used alone |
| Preseason minutes (veterans) | −0.02 (−0.06 to +0.02) | Not added (tie) |
| Preseason minutes (rookies) | −0.21 (−0.40 to −0.03) | **Added** |
| Return timelines by injury type (sprain 53%, strain 58%, soreness 54%, serious 24%, other 40% of remaining games) | −0.02 abs. / −0.04 squared error, both better | **Added** (means, since BPV is an expected value) |
| Team minutes scaled proportionally (instead of additive crowding) | +0.015 (−0.014 to +0.043) | Not added (tie) |
| Weekly totals using the latest injury report | weekly error 33.0 → 30.7 (−2.3, −2.8 to −1.8); −15 for listed players | **Added** ("this week" value) |
| One-IR-slot drafts: streaming credit q = league vs half vs none | league q drafted best on average | Current formula confirmed |
| Coaching changes (coach's past minutes concentration) | −0.005 (−0.016 to +0.009) | Not added (tie) |
| Weekly consistency | weak trait (0.23 year to year after controlling for level); <1 point of head-to-head win odds | Not added |
| **Weekly: team-aware injury-report lookup + "sat recently"** (a report lists only teams playing that day) | −2.2 FPTS/week (−2.5 to −2.0) vs the single-report version; 5 of 5 seasons | **Added** |
| **In-season shooting regression toward the player's own level** (eFG% vs last season) | −0.064 FPTS/game (−0.096 to −0.036); 4 of 5 seasons; also better for elite players | **Added** |
| Same, toward the league average | −0.048 overall but over-penalized efficient stars (elite error 4.12 → 4.65) | Rejected in favor of the own-level version |
| Shooting regression between seasons | +0.001 (−0.012 to +0.014) | Not added (tie) |
| Free-throw % regression | +0.000 (−0.004 to +0.004) | Not added (tie) |
| **This week's opponents** (fantasy points they allow) | −0.04 FPTS/week (−0.06 to −0.02); 5 of 5 seasons; practically negligible | **Added** |
| Home games this week | −0.004 (tie) | Not added |
| Deflections → steals, contested shots → blocks, potential assists → assists, rebound chances → rebounds (tracking) | predict the individual stat slightly better, but FPTS ties (−0.016 combined, −0.042 to +0.007) | Not added |
| Shot quality by defender distance ("shooting luck") | adds nothing beyond plain eFG% | Not added |
| Stat-specific roster crowding (rebounds, assists, shots) | +0.003 (−0.015 to +0.021) | Not added (tie) |
| Arena scorekeeper generosity | real and persistent for assists (year-to-year 0.58) but worth ~0.06 FPTS/game; no effect on team-changers | Not added |
| BPV–ESPN disagreement → wider ranges | disagreement doesn't predict error (correlation −0.003) | Not added |
| Post-injury ramp-up (first games back at ~83%, then ~95%) | current method already handles it (best version 3 of 5 seasons, tie) | Not added |
| 2023 participation policy → star availability | no detectable lasting effect | Not added |
| Back-to-backs and age for the weekly value | −0.019 (−0.050 to +0.018) | Not added (tie) |
| Remaining schedule strength (rest of season) | −0.008 (−0.018 to +0.000) | Not added (tie) |
| Returning teammate (reverse of the injury boost) | −0.018 for affected (−0.039 to +0.002) | Not added (tie) |
| Mid-season trades (crowding on the new team) | +0.002 (tie) | Not added |
| Second-year jump / high-pick development / second-half weighting | all ties | Not added |
| 65-game award threshold | chasing players actually played less; tie on 26 cases | Not added |
| **Preseason projection (BPV + ESPN) as the early-season prior** | −0.064 FPTS/game (−0.102 to −0.025); 3 of 4 seasons; top 10% tie | **Added** |
| Rookie preseason minutes in the early-season prior | +0.011 (−0.125 to +0.136) | Not added (tie) |
| Smooth age curve instead of six brackets | −0.003 (−0.023 to +0.018) | Not added (tie) |
| Replacement level at the 100th/160th/190th/220th player instead of 130th (standard draft field) | all lower than 130th on average (−69 to −122 team FPTS); 0–1 of 4 seasons better | Not changed |
| **In season: current absence streak (regulars not listed Out injured)** | −0.0034 availability error (−0.0049 to −0.0023); 4 of 5 seasons, 5 of 5 by squared error; −0.02 for absent players | **Added** |
| Next-season availability: age, minutes, playoff minutes, past serious injuries, body parts, end-of-season absences, absence patterns, trend, body size, usage, team record, experience, all combined (23 tests, vs history and vs ESPN) | all ties or worse | Not added |
| In season: this season's absences counted 2–5×; age; report status; non-injury Out; recent return from a long absence | ties or worse (2× helps average error but not squared error) | Not added |

**Holdout test on untouched seasons (2026-09-28).** To check whether the additions were luck, today's formula was frozen and run on 2014-15 to 2018-19, five seasons never used for any decision. The pass criteria were written down first (`docs/holdout-preregistration.md`); the test is `analysis/holdout.py`. The ESPN blend and injury-report features couldn't be tested (no data for those years). **8 of 9 checks passed:**

| Check | Result | |
|---|---|---|
| P1 Preseason ranking vs last season's totals | better in 4 of 5 | Pass |
| P2 Preseason ranking vs the original formula (80/20 × career GP%) | better in 3 of 5 (needed 4); average 0.708 vs 0.697 | **Fail** |
| P3 Age + roster crowding (additions) | ranking better in 5 of 5; per-game error −0.19 (−0.26 to −0.11) | Pass |
| P4 Simulated drafts vs naive and original | 4 of 5 and 3 of 5; average team 27,060 vs 26,290 (original) and 25,030 (naive) | Pass |
| P5 In season vs the original 80/20 | 5 of 5; error 3.64 vs 3.84 FPTS/game (−0.20, −0.27 to −0.13) | Pass |
| P6 Recalibration; shooting regression (additions) | 4 of 5 (−0.09); 5 of 5 (−0.01, small) | Pass |
| P7 Early-season prior vs season-to-date | 5 of 5; 3.68 vs 4.49 FPTS/game | Pass |
| P8 Shrunk availability vs career GP% | 5 of 5 | Pass |
| P9 Absence streak (addition) | 5 of 5 by squared error | Pass |

Every addition that could be tested held up on seasons it had never seen, so none is removed. The failure is the preseason ranking against the original formula: BPV's ranking edge over it is small and inconsistent (the original was better in 2014-15 and 2017-18), while BPV is clearly better per game, in season, and in drafts on average. The ESPN blend, which improved preseason rankings most in recent seasons, couldn't be part of this test.

**ESPN blend on two more seasons.** ESPN's archive also has genuine preseason projections for 2018-19 and 2020-21 (2017-18 was updated after opening night; 2019-20 is broken). The frozen hybrid, with rules written first (`docs/holdout-preregistration.md`, addendum; `analysis/holdout_espn.py`):

| | 2018-19 | 2020-21 |
|---|---|---|
| Per-game error: BPV / ESPN / hybrid | 4.32 / 4.51 / **4.12** | 4.38 / 4.32 / **4.18** |
| Ranking (rank correlation): BPV / ESPN / hybrid | 0.648 / 0.663 / **0.681** | 0.701 / 0.7290 / **0.7291** (a dead heat) |
| Season-total error: BPV / ESPN / hybrid | 522 / 538 / **510** | 406 / 463 / **386** |
| Simulated drafts: hybrid vs ESPN | **27,800** vs 26,030 | 23,210 vs **23,830** (hybrid last of 5) |

By the pre-set rule the blend is confirmed (best per-game error and ranking in both seasons), but honestly: it is clearly better per game and on season totals, clearly better at ranking in 2018-19, only tied with ESPN at ranking in 2020-21, and lost the 2020-21 drafts.

**Stopping point.** The loop stopped when the last round added nothing and the remaining ideas fell outside what can be tested: shot difficulty (xFG%) and "gravity" exist only from 2025-26; referee crews, travel, altitude and play-type matchups are single-game effects (the one weekly version we could test, opponent strength, is worth 0.04 FPTS a week); betting props and ESPN's in-season projections have no free history; college stats, G League projections and contract data have no free source here. About 105 ideas have now been tested against the same five seasons, so some small "wins" may be luck; the 2026-27 season is the real test.

**Round 10: against the experts (2026-09-29).** Archived preseason rankings (data/rankings/, saved before each opener) showed FantasyPros' expert consensus beating the BPV + ESPN blend at picking the top 130 in 4 of 4 seasons, and ESPN's analysts in 3 of 4. A research review (reports/Beating fantasy basketball projections.md) produced seven ideas, tested under rules written beforehand (docs/prereg-round10.md: season-total error, 3 of 4 seasons, player-clustered interval excluding zero after a Holm correction, no harm to the top 50). Scripts: analysis/round10*.py.

| Candidate | Result vs current | Decision |
|---|---|---|
| Equal-thirds blend of BPV, ESPN and expert consensus (ranks turned into points) | Season totals −12 (4 of 4, p = 0.022, fails the correction); per game −0.17 to −0.24, 4 of 4. On a pool chosen only from preseason lists, totals −4 (2 of 4) | Not added (primary metric failed); worth tracking in 2026-27 |
| Same, weighted 50% to the consensus | Totals −10 (4 of 4, p = 0.065) | Not added |
| Consensus alone, turned into points | Totals +22 (worse, 0 of 4): it ranks the top well but its point values are coarse | Not added |
| ESPN's projected minutes × BPV's per-minute rate (or 50/50 minutes) | +0.04 / +0.00 FPTS/game; ESPN's minutes were no more accurate than last season's (3.07 vs 3.05 MAE) | Not added |
| More weight on outside sources for team changers, second-year and injury-news players | Totals +8 (worse, 1 of 4) | Not added |
| **Per-stat per-minute rates** (3 seasons, own half-life and padding per stat, fitted on 2012-13..2018-19) × last season's minutes | −0.12 FPTS/game in the blend (−0.17 to −0.07), 4 of 4, preseason top 50 −0.17. But flat or slightly worse in 2020-21 (+0.01) and 2022-23 (+0.03) | **Added** (passed the rule); the honest expected gain is about −0.05 |
| Per-stat aging on top of that | +0.02 (1 of 4) | Not added |
| Rookie prior from draft slot and age | −0.08 (−0.16 to +0.00), 12 of 16 seasons | Not added |
| Rookies: 75% ESPN + 25% draft-slot prior | −0.33 (−1.54 to +0.86), 86 rookies | Not added (too few) |
| **Incoming rookies, season totals: veterans' ESPN rule** (37.5% ESPN per game, ESPN games × 0.86; pool = every draftee ESPN projected preseason, never-played = 0; docs/prereg-rookie-espn.md, analysis/rookie_espn.py) | −82 season FPTS (−121 to −41), 3 of 4 seasons, top 10% −73, 103 rookies (2021-22 has only 8 and was +5). ESPN alone −49 (−138 to +43), not significant. Per game (20+ games) −0.67 | **Added** |

Where the gap to the experts lives: turned into points, the consensus is worse than the blend on season totals in every slice except players with known preseason injuries (16 players, −120). Games-played error is the largest part of season-total error for every source. Its edge is in ordering the top of the draft, not in point estimates.

## 17. What to try next

Ordered by expected value, based on our tests and published practice:

1. **Score BPV (now the BPV + ESPN hybrid) against competitors in 2026-27.** About 105 ideas have now been tested against the same five seasons, so one or two "wins" may be luck; a fresh season is the real test. Save BPV's rankings before the season (`python -m analysis.snapshot`) and save ESPN's and other sites' rankings the same week. Score them all when the season ends. Without this, no "most accurate" claim can be made. A peer-reviewed study of daily fantasy projections found professional forecasts beat naive ones only moderately, so expect small differences between good systems.
2. **A full minutes model.** Crowding (Section 13) is a first step. A depth-chart model that projects each player's minutes directly (as FiveThirtyEight did) could capture more, especially for players whose role changes without a roster change.
3. **A fuller weekly view**: the site now shows a tested "this week" value; adding the game-level teammate effect is untested.
4. **Contract-year effects**, if a clean source of contract data can be found (published results are mixed: possibly a dip the season after a new contract).
5. **Finer injury types** (e.g. hamstring vs calf strains) once more seasons of reports accumulate.
6. **Rest-of-season trade values** weighted by each team's remaining schedule.

See Section 16 for everything already tested, including what didn't work.

---

## Appendix A: What changed from the first draft

| First draft | Revision | Why |
|---|---|---|
| BPV = FPTS × career GP% | BPV = p·F + (1−p)·q·R | The first draft's own argument (Section 4): missed games aren't worth zero |
| Career GP%, assuming 82 games | Recent seasons weighted, shrunk, real schedules | Career GP% wasn't significantly better than the league average; shortened seasons and trades were miscounted |
| Separate reliability score, not defined | League-average q, plus manual injury input | A player's absence pattern can't be measured reliably from box scores (one season's reliability is about 0.12) |
| Cox × FPTS | Cox → calibrated availability (future work) | A hazard ratio above 1 means riskier, so multiplying by it rewards risk |
| Last 5 = team's last 5, games played only | Last 5 games played | Predicted slightly better in testing, and avoids 1–2 game samples |
| 20% recent weight (tuned informally) | Tested: 10–20% supported (20% vs 15% a statistical tie); split into minutes (0.3) and efficiency (0.1) | Measured out of sample, with bootstrap intervals |
| New Role Value 90%, 50/50, manual | Idea confirmed (about 1 FPTS/game better); 0.90 and 60/40 kept, but the haircut can't be pinned down (0.80–1.10) | Measured on 703 role changes |
| Not covered | Rookie and early-season baselines | Players without history were valued at 0 |
| One draft per experiment | 1,000 simulated drafts × 4 seasons + rank correlation, tuned only on earlier seasons | One trial can't separate skill from luck |
| Last season only, no age | Last season + age adjustment between seasons | 4.7% less preseason error; beat Basketball-Reference's projection system |
| Team shown = last season's team | Next season's rosters, plus roster crowding | Offseason moves were invisible; crowding cut preseason error 1.4% |
| Cox model proposed | Cox model built and tested on absences | Didn't beat the current availability estimate |
| No uncertainty shown | 80% likely range, fantasy-playoff games | Calibrated out of sample; playoff counts matter for head-to-head playoffs |
| Injuries entered by hand only | Official injury report read automatically in season | Serious injuries predict long absences with no hindsight |
| Projections used as-is | Recalibrated in season; expected fantasy-playoff FPTS allows for tanking | Both beat current BPV out of sample |
| No competitor comparison | Compared with ESPN's preseason projections; BPV + ESPN hybrid before the season | ESPN out-ranked plain BPV; the hybrid beat both |
| ADP = "average draft pick" | Average draft position | Standard term |
| "2–3 games a week" | About 3.4 | 82 games over roughly 24 weeks |

## Appendix B: Data and methods

- **Injury reports.** The NBA's official injury report PDFs, one per game day (the 5:30 PM Eastern report, or the nearest available), 2021-22 to 2025-26, parsed with `nbainjuries` 1.1.1.
- **Data.** NBA regular-season game logs (every player-game and team-game) for 2019-20 to 2025-26 and full draft history, from stats.nba.com via `nba_api` 1.11.4. NBA Cup championship games aren't in regular-season stats and are excluded.
- **Absence runs.** For each player-season we walk his games against his team's schedule. Every run of consecutive team games he missed is an absence.
  - Around a trade, the gap is measured on whichever team's schedule gives the shorter gap.
  - In a player's debut season, games before his first appearance don't count, since he may not have been signed yet.
  - Absences of 5+ straight games count as long (IR-able).
- **Shrinkage.** `estimate = (n·own + k·league) / (n + k)`. This is standard empirical-Bayes ("regression to the mean") weighting; see Efron & Morris (1975) and Tango's regression method. We chose k by testing values on past seasons.
- **Backtest design.**
  - Tuning seasons: 2021-22 to 2024-25. Test season: 2025-26.
  - Checkpoints every 7 days from 4 weeks into the season to 3 weeks before the end.
  - Error is the mean absolute difference between the predicted and actual rest-of-season FPTS per game, for players with at least 10 games before and after the checkpoint and at least 12 minutes per game.
- **Reproduce everything:** `python -m analysis.backtest` rewrites `analysis/results.json`. `python -m analysis.test_injury_reports`, `analysis.test_research_ideas`, `analysis.test_research_followup`, `analysis.test_cox`, `analysis.test_minutes_model`, `analysis.test_misc`, `analysis.test_teammates_perstat` and `analysis.test_schedule_positions_uncertainty` rerun the Section 16 tests. `python -m analysis.preseason_production` reruns Section 13 and `python -m analysis.decay_test` the exponential-decay comparison. `python -m analysis.robustness` reruns the checks behind the confidence intervals (resampling whole players, 300 times), the per-season results, the comparison tuned only on earlier seasons, and the absence-pattern reliability tests. It writes `analysis/robustness.json`.

## Appendix C: Calibrating a risk percentile into availability

1. For past seasons, give every player a risk score at the start of the season (from Cox, or any model).
2. Group players into percentile buckets (for example, deciles).
3. For each bucket, record the share of games those players actually played that season.
4. A player's availability is his bucket's observed share. If buckets are small, fit a smooth curve through them or merge neighboring buckets.
5. Use that availability as p in BPV. Then blend in the player's own record with the shrinkage formula, since a risk model and a player's history each carry information.

## References

- ESPN, "ESPN Fantasy's default points-league scoring explained" (2025). espn.com/fantasy/basketball/story/_/id/30296896
- ESPN, "ESPN Fantasy Basketball 101: Adjusting the settings" (rosters, default playoffs). espn.com/fantasy/basketball/story/_/id/20800285
- ESPN Fan Support: IR eligibility (article 360046053592); Waiver Order (article 360000959372). support.espn.com
- Jha, A. (2025, September 28). "Figuring out why NBA players get injured using Cox Proportional Hazards." Medium.
- Herzog, M. M., Brink, A., Gondalia, R., DiFiori, J. P. & Mack, C. D. (2026). "The relationship between games missed for rest or load management and injury in the NBA, 2014–15 through 2022–23." *Sports Medicine* 56(9):2313–2323.
- Menon, A. et al. (2024). Season-ending injuries in the NBA: more minutes per game and later in the season (3rd/4th quartiles) raise risk. *Arthroscopy* 40(9):2468–2473.
- Medvedovsky, K. (2020, August 6). "NBA stabilization rates and the padding approach." kmedved.com
- Miller, J. & Sanjurjo, A. (2018). "Surprised by the hot hand fallacy?" *Econometrica* 86(6).
- Bocskocsky, Andrew, Ezekowitz, J. & Stein, C. (2014). "The hot hand: a new approach to an old 'fallacy'." MIT Sloan Sports Analytics Conference.
- Efron, B. & Morris, C. (1975). "Data analysis using Stein's estimator and its generalizations." *JASA* 70(350):311–319.
- Davidson-Pilon, C. *lifelines* documentation (CoxPHFitter, proportional hazards checks).
- Bryant, J. "Principles of Value Based Drafting." Footballguys (VBD introduced 1996).
