# Projecting NBA Minutes and Per-Minute Production (Component Stats)

Research date: 2026-09-29. About 17 tool calls. Public, quantitative, NBA-specific evidence is thin for several of these questions. Where the evidence is baseball or practitioner lore, it is labeled.

Context for the reader: BPV currently projects ESPN points-league FPTS/G preseason as follows: last-season FPTS/G, plus an age bucket, plus roster crowding, blended 37.5% with ESPN. Tested and rejected: per-stat recency, per-stat age, per-stat padding, a usage-weighted teammate boost, proportional team minutes, older seasons and decay windows, and a coaching-change flag.

## 1. Minutes projection: separating playing time from per-minute rates; rotation and 240-minute budget; team changes

### Takeaway
Every serious system models minutes separately from per-minute or per-possession rates. Minutes are the hardest and fastest-changing input. DARKO sets its minutes and starter "role" signal half-life at about 1–2 games, compared with seasons for shooting skill. DARKO's own authors say minutes is the one stat where it lost to DFS-site projections. I found no public quantitative evaluation of a 240-minute team-budget redistribution model beating naive last-season minutes preseason.

### Cited Findings
- DARKO applies per-stat exponential decay (weight β^t, t = days ago). The published half-lives are: starting role about 1 game, minutes role about 2 games, 3P% about 1.5 seasons, FT% about 1.4 seasons, % at rim about 2.5 seasons, corner-3 % about 8 seasons — [DARKO About](https://www.darko.app/about)
- DARKO calls minutes "the hardest thing any projection system forecasts." It projects minutes from recent playing time and role, and minutes was "the only stat where DARKO lost" against DFS sites — [DARKO About](https://www.darko.app/about)
- DARKO beat DFS projections on points, rebounds, assists, blocks, turnovers and 3PM. No margins are published on the page — [DARKO About](https://www.darko.app/about)
- DARKO's season-level team win projections use minutes projections from a different analyst (BaskMonster) layered on DARKO per-possession ratings. The rate model and the minutes model are kept as separate modules — [Power Rank podcast / search summary](https://thepowerrank.com/2022/05/27/podcast-kostya-medvedovsky-on-the-darko-nba-player-projections/)
- When a player changes teams, DARKO "gets less confident in its understanding of a player's talent." In effect it raises the learning rate (Kalman process noise) for that player — [DARKO About](https://www.darko.app/about)
- Between seasons, DARKO "pulls its projections back toward average" — [DARKO About](https://www.darko.app/about)
- DFS practitioner framing: 240 team minutes (48 per position). The three main drivers of rotation change are injuries, role changes and blowouts, and injuries matter most — [RotoGrinders](https://rotogrinders.com/fantasy/lessons/accurately-predicting-minutes-nba-dfs); [RotoWire projected minutes explainer](https://www.rotowire.com/basketball/article/nba-projected-minutes-explained-fantasy-basketball-97473)
- When a star is out, the team's offensive "budget" is redistributed, not reduced: option 2 takes option 1's shots and a bench player gets the start and more minutes. Practitioner claim, no coefficients — [NBAstuffer](https://www.nbastuffer.com/what-changes-when-star-teammate-out/)
- In a PLOS One study (2024) of in-game injuries from 2002–2021 as natural experiments, only players who were both All-Stars and captains measurably affected teammate performance (efficiency) after leaving — [PMC11563377](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11563377/)
- Aging and minutes: in DSMok1's APBRmetrics matched-pairs work, WS/48 peaks at about 26, and minutes start dropping significantly at about 27 — [APBRmetrics aging thread](https://www.apbr.org/metrics/viewtopic.php?t=125)
- Basketball-Reference's Simple Projection System (SPS) projects per-minute stats with seasons weighted 6/3/1, regressed toward a league average scaled to 1000 minutes, with an age adjustment. It is described as "easy and fun," not definitive — [BBRef projections methodology](https://www.basketball-reference.com/about/projections.html)

### Inferences
- A stronger version of BPV's rejected "proportional team minutes" and "roster crowding" ideas is a two-stage model. Stage 1 projects each player's *share* of the 240×82 team minutes. It combines last-season MPG (heavily recency-weighted), games-played/health history, the age-minutes curve, and a rank-within-team talent signal such as prior-season BPM or FPTS/36. Shares are normalized within each team so they sum to 240 per game, with each player capped near 36–38 MPG. Stage 2 multiplies by per-minute rates. The normalization is the key difference from "proportional" scaling: an arrival takes minutes from the players ranked nearest them at that position or talent tier, not from everyone equally.
- The evidence says minutes is where even elite systems lose to human-informed sources (DFS sites). So BPV's 37.5% ESPN blend is probably doing most of its useful work on the *minutes* side. A cleaner design would take ESPN's implied minutes, or ESPN FPTS divided by BPV's per-minute rate, and blend on the minutes component alone. BPV would then keep its own rate estimate. This is a testable decomposition: back out ESPN's implied MPG, then check whether BPV rate × ESPN minutes beats both BPV total and ESPN total.
- The rejected coaching-change flag has no supporting public evidence. That is consistent with it not helping.
- For team changers, the DARKO-style fix is not a mean shift. It is *wider uncertainty*: regress the minutes projection harder toward a role prior (e.g., the historical median MPG change for players who switch teams at similar prior MPG).

### Gaps
- I found no public RMSE for minutes models (e.g., a 240-budget model vs. last-season MPG vs. ESPN) at the season level.
- There are no published coefficients for how much a new teammate's minutes displace incumbents, by position or talent rank.
- I found nothing on contract-year effects on minutes or production.
- DARKO's full technical write-up (β per stat, prior strength) is not public beyond the About page summary.

## 2. Component (per-stat) projection vs. projecting a single fantasy-point total

### Takeaway
Industry practice across sports (DARKO, BBRef SPS, fantasy football/baseball projection systems) projects components and aggregates them with the scoring formula. The rationale is that components stabilize, age and decay at different rates, so one decay or regression parameter on the total is wrong for most of its parts. I found no head-to-head NBA study quantifying component vs. total accuracy for fantasy points. BPV's own failed test of per-stat recency, age and padding is a data point against assuming the gain is large.

### Cited Findings
- DARKO projects "every box-score stat separately — shooting, rebounding, assists, turnovers ... each with its own decay rate (three-point shooting takes far longer to trust than rebounding)" — [DARKO About](https://www.darko.app/about)
- BBRef SPS projects makes and misses separately, derives attempts, then computes points from projected FG/3P/FT. For negative stats (misses, TOV, fouls) the sign of the age adjustment is reversed — [BBRef projections](https://www.basketball-reference.com/about/projections.html)
- Fantasy-projection practitioners describe the component approach as the "common skeleton" of projection models, citing interpretability and error cancellation. This is argument, not measured evidence — [Fantasy Projection Lab](https://fantasyprojectionlab.com/projection-models-explained/); [RotoGrinders](https://rotogrinders.com/articles/how-to-accurately-project-player-fantasy-scores-16415)
- Joint multi-metric career-trajectory modeling (17 metrics) improves held-out predictive performance over single-metric models, even for an individual metric such as OBPM. This is evidence that component structure carries shared information — [Brahme & Franks, arXiv 2609.33752, Sept 2026](https://arxiv.org/html/2609.33752)

### Inferences
- The theoretical case for components: ESPN points-league FPTS is dominated by PTS, REB and AST. Their stabilization differs, and so do their aging directions: REB and BLK decline early, AST rises late. A single regression on the total mixes these. The error from mixing shrinks, though, when (a) per-minute FPTS is itself highly stable year to year and (b) most variance is in minutes. Both are probably true for established players, which likely explains why BPV's per-stat test failed.
- Where component modeling most plausibly helps: (i) young players, where the BLK/OREB-early vs. AST/3PA-late aging split matters most; (ii) players with fluky shooting seasons. 3P% and FT% are slow to stabilize, so points from made threes should be regressed much harder than rebounds; (iii) team changers, where REB/AST shares are context-dependent and FT% is not.
- A fair test for BPV is to regress each component toward a *position/role-specific* prior with stat-specific shrinkage (see section 3) and project minutes separately. BPV should compare *per-minute FPTS* accuracy (component vs. total) with minutes held fixed at actual. That isolates whether components help the rate side at all.

### Gaps
- There is no published NBA backtest of component-sum vs. direct-FPTS projection. The closest evidence is DARKO beating DFS sites per stat, but DFS sites also use components.
- I found no evidence on correlated errors between components, e.g., usage-driven PTS and AST moving together.

## 3. Stat stabilization / reliability in the NBA and how to regress each stat

### Takeaway
Hard public NBA numbers exist mainly for shooting percentages: 3P% needs about 750 attempts to reach 0.7 reliability (Blackport, 2014) and FT% needs about 300 attempts. Rate stats (REB%, 2P%) are said to stabilize much faster, but I did not find a sourced per-stat possession table for REB/AST/STL/BLK/TOV/USG. The standard implementation is the Tango/Marcel regression constant: true rate ≈ (obs×n + prior×k)/(n+k), where k is the sample size at which reliability = 0.5.

### Cited Findings
- 3P%: about 750 attempts to cross 0.7 reliability (KR-21 split-half). The single-season record for 3PA was then 678, so most players never stabilize within a season. Darryl Blackport, Nylon Calculus, Aug 29 2014 — [FanSided/Nylon Calculus](https://fansided.com/2014/08/29/long-take-three-point-shooting-stabilize/). The article also cautions that the figure describes past-sample reliability, not predictive validity.
- FT%: about 300 attempts (secondary aggregator statement, primary study not located) — [search summary; primary source not verified]. **Treat as unverified.**
- 2P% and rebounding rate "stabilize quickly." Three-point percentage "can take years." Royce Webb, Mar 14 2026, with no per-stat numbers — [roycewebb.com](https://www.roycewebb.com/p/how-to-accurately-predict-nba-player)
- In team-level terms, style stats (pace, shot selection) are trustworthy within a few games, but opponent 3P% is trustworthy only near season's end — [Nylon Calculus, Dec 2017](https://fansided.com/2017/12/21/nylon-calculus-team-stats-noise-stabilization-thunder/)
- DARKO's fitted decay half-lives are an implicit ordering of how much history each stat needs: FT% about 1.4 seasons, 3P% about 1.5 seasons, rim % about 2.5 seasons, corner-3 % about 8 seasons, minutes/starter about 1–2 games — [DARKO About](https://www.darko.app/about)
- BBRef SPS uses one regression amount for all stats: 1000 minutes of league-average production (weighted by season weights) — [BBRef projections](https://www.basketball-reference.com/about/projections.html)
- Baseball analogue: the Marcel projection system uses a 5/4/3 season weighting and adds about 1200 PA of league-average performance, with an age adjustment. It is the canonical "minimum competent" benchmark that more complex systems often barely beat — [Tangotiger Marcel](http://www.tangotiger.net/marcel/) (baseball; URL from general knowledge, page not fetched this session)
- Bayesian binomial approach for FG%, i.e., beta prior / empirical Bayes per shot type — [Rao-Blackwellizing FG%, arXiv 1808.04871](https://arxiv.org/pdf/1808.04871); [roycewebb.com PyMC example](https://www.roycewebb.com/p/how-to-accurately-predict-nba-player)

### Inferences
- Implementation from box-score game logs:
  1. For each stat compute a per-opportunity rate: 3P% per 3PA, FT% per FTA, 2P% per 2PA, REB/AST/STL/BLK/TOV/FGA/FTA/3PA per minute (or per 36).
  2. Estimate k per stat with split-half reliability: randomly split each player's games into halves and compute the correlation r between halves. Then k ≈ n_half × (1−r)/r. Equivalently, estimate between-player true variance vs. binomial/Poisson noise variance: k = mean/var_true for Poisson-rate stats, or p(1−p)/var_true − 1 for percentages.
  3. Regress toward a *position- or role-conditioned* prior, not the league mean. For example, center BLK/REB priors differ by 3–5× from guard priors, so a league-mean prior over-shrinks bigs.
  4. The expected ordering, from the evidence above plus general Poisson logic: rare events (BLK, STL) and percentages (3P%, FT%) need the most regression; high-frequency role stats (REB/min, FGA/min, AST/min) need the least. BPV's "padding" test may have failed if it used one pad for all stats or a league-mean prior.
- Stabilization is about noise in the *observed* rate, whereas decay is about *true* talent drift. Both are needed, and they are separate parameters.

### Gaps
- I did not find a sourced NBA per-stat stabilization table (possessions or minutes) for REB%, AST%, STL%, BLK%, TOV%, USG%, even though such tables are often cited informally. The report writer should not quote specific numbers for these without a source.
- The FT% 300-attempt figure is from an aggregator, and the primary study was not verified.

## 4. Aging curves per stat and survivorship-bias-free estimation

### Takeaway
Athleticism stats (BLK, OREB) peak earliest, around 20–23. FT%, 2P% efficiency and steals peak mid-20s. Assists and 3PA volume keep rising into the early 30s. Overall value peaks around 26–27, and minutes begin falling around 27. The delta (matched-pairs) method is standard but survivor-biased. Remedies include regressing both seasons before differencing (DSMok1), survival/censoring models (Brahme & Franks 2026, Gompertz hazard), and multiple imputation of missing seasons (baseball).

### Cited Findings
- Blocks and offensive rebounds peak about ages 20–23. FT%, 2P efficiency and steals peak about 24–26. Assists and 3PA volume keep rising into the early 30s. The principal-component analysis separates early-peaking stats (REB, BLK, defense, 2P efficiency) from late-peaking 3PA volume. About 2,300 players, 1997–2026, 17 metrics — [Brahme & Franks, arXiv 2609.33752, Sept 27 2026](https://arxiv.org/html/2609.33752)
- That paper handles survivorship with a Gompertz proportional-hazards survival component, because "less productive athletes retire earlier," and uses a concave (single-peaked) process prior. Joint modeling beats single-metric models on held-out predictive density — [same](https://arxiv.org/html/2609.33752)
- Older players are worse than expected at some types of rebounding and at stealing, and better than expected at shooting and assisting — [search summary citing Harvard Sports Analysis, 2017](https://harvardsportsanalysis.org/2017/11/what-happens-to-nba-players-when-they-age/) (page returned HTTP 500, so content not directly verified)
- Blocks tend to peak at the very start of careers, and the best-fit overall peak is about 27. Kevin Pelton, ESPN, Dec 11 2017 — [ESPN](https://www.espn.com/nba/story/_/id/21735830/kevin-pelton-lebron-james-breaking-aging-curve-nba)
- DSMok1 (APBRmetrics): matched pairs with 100+ minutes in consecutive seasons, using *regressed* WS/48 to reduce survivor bias. Peak at 26, and minutes drop significantly at about 27, suggesting players are past peak — [APBRmetrics](https://www.apbr.org/metrics/viewtopic.php?t=125)
- BBRef SPS applies a linear age multiplier: +0.4%/yr below 28 and −0.2%/yr above 28 (sign reversed for negative stats), identical for all stats — [BBRef](https://www.basketball-reference.com/about/projections.html)
- DARKO uses independent aging curves for each statistic, accounting for selection bias — [DARKO About](https://www.darko.app/about)
- Baseball analogue: multiple imputation of unobserved seasons to correct delta-method survivor bias — [arXiv 2210.02383](https://arxiv.org/pdf/2210.02383); functional-data aging curves — [arXiv 1403.7548](https://arxiv.org/pdf/1403.7548)

### Inferences
- For ESPN points (PTS, REB, AST, STL, BLK, TOV, shooting makes and misses), a per-stat age adjustment matters most for young bigs (BLK/OREB already near peak at 22–23 while AST/3PA still grow) and for aging bigs (REB/BLK decline while AST holds). BPV's age bucket on total FPTS averages these out. That is probably fine for wings and a source of error at the extremes. A sensible test is per-stat age deltas estimated with the delta method on *regressed* per-minute rates, with pairs weighted by the harmonic mean of minutes, restricted to C/PF vs. G subsets.
- A practical survivor correction for game logs: include player-seasons whose next season is missing by imputing a replacement-level "phantom" season (e.g., 25th percentile of same-age rate), or weight pairs by the harmonic mean of minutes. Harmonic-mean weighting is standard FanGraphs practice (baseball; not sourced this session).

### Gaps
- There are no sourced numeric per-year NBA deltas per stat (e.g., BLK% −x% per year after 25). The Brahme & Franks figures would have these but were only summarized.
- The Harvard Sports Analysis article was not directly verifiable.

## 5. Recency weighting: exponential decay per stat, Kalman filters

### Takeaway
DARKO is the reference implementation. It uses per-stat exponential decay with β fit by differential evolution to maximize out-of-sample accuracy, plus a modified Kalman filter with increased uncertainty on team changes and preseason regression toward the mean. Role and minutes decay in games, and shooting skill decays over seasons. BBRef SPS (6/3/1) and baseball Marcel (5/4/3) show the simple season-weighted baseline.

### Cited Findings
- Decay weight β^t by days, β fit per stat via differential evolution. β near 1 means equal weight on all history — [DARKO About](https://www.darko.app/about); [nbastuffer DARKO explainer](https://www.nbastuffer.com/analytics101/darko-daily-plus-minus/)
- Kalman filter: "each game is a new noisy reading of a player's true skill ... weighting by how reliable each source is" — [DARKO About](https://www.darko.app/about)
- Half-lives: role about 1 game, minutes about 2 games, FT% about 1.4 seasons, 3P% about 1.5 seasons, rim % about 2.5 seasons, corner 3 % about 8 seasons — [DARKO About](https://www.darko.app/about)
- SPS season weights 6/3/1 for three seasons — [BBRef](https://www.basketball-reference.com/about/projections.html)

### Inferences
- The evidence implies different optimal decay per stat. BPV found "older seasons / decay windows" did not help the *total*. That is consistent with a mixture: fast-decaying components (minutes, usage/role) wash out the gain from slow-decaying ones (FT%, 3P%). The stronger version: fit β separately for (a) MPG, (b) per-minute FGA/FTA/3PA (role/usage, likely fast), (c) per-minute REB/AST/STL/BLK/TOV (likely intermediate), (d) FG%/FT%/3P% (slow, many seasons). Then recombine.
- Kalman local-level model per stat rate: state x_t = x_{t−1} + w (var Q), observation y_t = x_t + v (var R/minutes). The steady-state gain K ≈ equivalent exponential decay, so fitting Q/R per stat on game logs is the same problem as fitting β. On a team change, add extra Q, per DARKO.

### Gaps
- DARKO's β values for REB/AST/STL/BLK/TOV/PTS rates are not published on the About page (only the shooting and role half-lives above).
- There is no public ablation showing how much DARKO's per-stat decay improves over uniform decay.

## 6. Pace and team context effects on counting stats

### Takeaway
Counting stats scale with possessions, so pace-adjusting (per-100 or per-possession rates × projected team pace) is standard practice (DARKO works per possession). Team context also creates diminishing returns: rebounds, and to a lesser extent other opportunity-limited stats, are partly zero-sum among teammates. Coefficients are old and contested.

### Cited Findings
- DARKO models per-possession box-score stats and converts to totals using minutes and pace; its win projections combine per-possession ratings with minutes projections — [DARKO About](https://www.darko.app/about); [Power Rank podcast summary](https://thepowerrank.com/2022/05/27/podcast-kostya-medvedovsky-on-the-darko-nba-player-projections/)
- Diminishing returns in rebounding: regression slopes of about 0.7 for offensive and about 0.3 for defensive rebounds (team rebound% change per unit of summed individual rebound%). Adding an elite defensive rebounder barely moves team DREB%. Sport Skeptic (Dec 2010), summarizing earlier studies and critiquing their measurement — [Sport Skeptic](https://sportskeptic.wordpress.com/2010/12/04/diminishing-returns-in-the-nba/)
- Every extra rebound by a center goes with about 0.61 fewer rebounds by teammates (from search summary of the Birnbaum/APBR discussion; the primary page failed to load) — [Birnbaum blog](http://blog.philbirnbaum.com/2011/01/do-players-steal-rebounding.html); [APBRmetrics](https://apbr.org/metrics/viewtopic.php?t=8223)
- Style stats such as pace stabilize within a few games at team level — [Nylon Calculus 2017](https://fansided.com/2017/12/21/nylon-calculus-team-stats-noise-stabilization-thunder/)

### Inferences
- For BPV: the "usage-weighted teammate boost" test likely failed partly because DREB is heavily zero-sum while usage (FGA) is the most redistributable. A stronger version would give each stat its own displacement coefficient: DREB displacement high (about 0.6–0.7 of a new teammate's rebound rate taken from same-position incumbents), OREB lower, FGA/usage moderate, and FT% none. Coefficients should be estimated on the user's own data from team changers, because public figures are 2010-era.
- The pace effect on season-level fantasy points is probably small relative to minutes (team pace spreads are a few percent, and team pace is itself projectable). It is still cheap to include: projected team possessions/48 × per-possession rate.

### Gaps
- There is no modern (post-2015) quantification of per-stat diminishing returns across teammates.
- There is no evidence on whether pace adjustment measurably improves season-level fantasy projections vs. per-minute rates.

## Overall bottom line for BPV (inference)
- The published evidence supports the *architecture* of a separate minutes model, per-stat rates with stat-specific regression and decay, per-stat aging, and more uncertainty for team changers. It does **not** give a quantitative guarantee that this beats a well-regressed total-FPTS projection plus a good external source for minutes.
- DARKO, the best public system, loses on minutes to human-informed sources. That suggests BPV's biggest lever is probably not more rate modeling. It is using ESPN (or another human source) for the minutes component and BPV's own regressed per-minute rate. That decomposition is testable with existing data.
- Rejected tests to revisit with the stronger form: per-stat padding needs stat-specific k and position priors, not one pad; decay needs stat-specific β and a separate minutes decay; teammate effects need per-stat displacement with 240-minute normalization.
