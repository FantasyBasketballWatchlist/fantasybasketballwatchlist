# Minutes and Usage Modeling for Single-Game NBA Projections (esp. teammate absences)

Scope note: About 16 search/fetch calls. Public, primary methodology from the professional systems (DARKO, ETR, SaberSim, Basketball Monster, numberFire) is very thin. Their minutes and injury logic is proprietary or only discussed in podcasts. Most citable material is DFS-education articles (RotoGrinders, Stokastic), Basketball-Reference and Neil Paine blog posts, and a squared2020 post. No published study I found reports the MAE gain from adding teammate-absence features to single-game projections. Treat the "Inferences" bullets as reasoning, not evidence.

## 1. How do professional projection systems project minutes for a game?

### Takeaway
The public descriptions all treat minutes as the dominant input: projection = minutes x per-minute rate. They build minutes from a blend of season and recent averages. Then they adjust by hand or by rules for injuries (the biggest factor), role changes and blowout risk (point spread), and they re-run close to tipoff for late news. No major vendor publishes its minutes algorithm.

### Cited Findings
- DARKO stands for "Daily Adjusted and Regressed Kalman Optimized" projections. It is updated daily, learns from every game a player has played, and weights recent performance more heavily (Medvedovsky quoted). It is designed to remove noise and luck. — [Liberty Ballers](https://www.libertyballers.com/2019/12/8/20997234/the-sixers-past-present-and-future)
- Medvedovsky discussed DARKO's Kalman filter and exponential decay on a 2022 podcast, but no written decay rate or formula was found. — [The Power Rank podcast](https://thepowerrank.libsyn.com/kostya-medvedovsky-on-the-darko-nba-player-projections)
- A secondhand forum claim says DARKO used Basketball Monster's preseason minutes projections for team-win contests, and LEBRON and other models used Kevin Pelton's minutes. In other words, even top player-rating modelers have outsourced minutes. — [APBRmetrics forum](https://apbr.org/metrics/viewtopic.php?p=38518) (unverified, forum post)
- A forum commenter warns that actual minutes are suppressed for the best players in blowouts, which biases evaluation against actual minutes. — [APBRmetrics](https://apbr.org/metrics/viewtopic.php?p=38970)
- RotoGrinders gives a baseline minutes formula: 0.75 x season MPG + 0.25 x last-5 MPG. Its three main drivers of rotation change are injuries (the most influential), role changes and blowouts. Its blowout rule starts at a 7-point spread and cuts 1.5% of projected minutes per point beyond that (32 min becomes 31.52 at 8, 30.56 at 10, 28.64 at 14). Expect "a couple extra minutes" in games projected to be close. Underdog players carry more blowout risk than favorites. Don't mistake blowout-inflated bench minutes for a role change. — [RotoGrinders lesson](https://rotogrinders.com/fantasy/lessons/accurately-predicting-minutes-nba-dfs)
- Stokastic says the season average is "a baseline, not an answer." It recommends weighting recent games when a role changes (for example, bench to starter) and using game logs and substitution patterns to understand rotation and starter rest. It also notes wide minute distributions (Mitchell Robinson ranging 14-28 minutes). — [Stokastic](https://www.stokastic.com/articles/nba-dfs/nba-dfs-research)
- Stokastic: "Confirm the minutes before trusting the usage." A 26% usage rate is middling at 24 minutes and strong at 34. Projected minutes can drop sharply on large spreads or when a team's seed is locked. — [Stokastic usage strategy](https://www.stokastic.com/articles/dfs-strategy/nba-dfs-usage-rate-strategy)
- A 2014-era projection model normalized team minutes to 5 x 48.4 per game (the extra covers overtime) and cut injured players' stats by the expected missed share. — via search summary of [RotoValue blog](https://blog.rotovalue.com/?p=370)
- A Basketball-Reference SPM projection used a tiered rule: a team's top 5 minutes-earners use about 60% of team player-minutes. — [Basketball-Reference blog](https://www.basketball-reference.com/blog/indexcc8b.html?p=3361)
- SaberSim has podcast episodes on how it calculates projected NBA minutes, handles injuries in its sims and reacts to breaking news. The show notes don't give the method. — [SaberSim DFS Q&A: minutes](https://sabersim.castos.com/episodes/dfs-qa-how-is-sabersim-calculating-the-projected-minutes-for-nba), [injuries](https://sabersim.castos.com/episodes/dfs-qa-are-injuries-accounted-for-in-the-sims), [breaking news](https://sabersim.castos.com/episodes/dfs-qa-nba-breaking-news-and-the-sims)
- A non-authoritative, privately hosted props-model spec proposes minutes = 40% L5 + 30% L10 + 20% L20 + 10% season, plus back-to-back and blowout-probability factors. — [edge-assist spec](https://edge-assist.duckdns.org/data-status/docs/nba-player-props/ruling/NBA%20Player%20Props%20Data%20Audit%20Council%20Ruling) (low reliability, no validation shown)

### Inferences
- Industry practice runs on a "team minutes budget": 240 minutes (more with overtime) per team, allocated across the active roster. When someone is ruled Out, the budget is re-allocated rather than each player's minutes being projected independently. This is the single most implementable structural change for a model that projects each player's minutes independently. Re-normalizing to 240 automatically produces the "teammate out, minutes up" effect.
- The existing model's 3-game half-life is more reactive than the published heuristics. RotoGrinders' 75/25 season/L5 weighting is about a 10+ game effective window. A fast decay helps after genuine role changes but chases blowout and foul-trouble noise. A sensible design is a slower base decay plus explicit role-change triggers: a starter flag change, or a teammate returning or leaving.
- Blowout adjustment from the point spread (about 1.5% of minutes per point beyond 7) is a cheap, documented heuristic. I found no evidence of its calibration, so it should be fit on your own data: regress realized minutes / projected minutes on |spread|, separately for starters and bench.

### Gaps
- No primary documentation of how DARKO, ETR, Basketball Monster, FantasyLabs, numberFire or Rotowire compute single-game minutes, handle minutes restrictions, or model foul trouble. ETR's and Rotowire's minutes are widely believed to be analyst-curated, but I found no citable source.
- No source quantified foul-trouble effects or minutes-restriction adherence (for example, how often "restriction ~20 min" players exceed it).
- FiveThirtyEight's methodology page (it had a depth-chart and injury-based playing-time system) now redirects to ABC News and could not be fetched.

## 2. Usage redistribution when a teammate is out: methods and effect sizes

### Takeaway
The standard practitioner method is "usage vacated": the missing player's possessions (and minutes) are redistributed, mostly to the remaining creators and positional replacements. The effect concentrates when only one creator remains and splits when two same-position players share the role. Rebounds and assists are more role-driven than usage, so they shift more predictably with roster changes. No rigorous public quantification exists. The only parameterized "cascade" scheme found is unvalidated.

### Cited Findings
- Usage spikes can be very large in extreme cases. LeVert ran 41.3% usage and a 33.9% assist rate over 261 minutes with Brooklyn's creators out (2019-20). Beal's absence vacated 34.5% usage and 36 MPG. Simmons' assist% was about 32% with Embiid on and Milton off versus 23.5% with Milton on. — [Stokastic](https://www.stokastic.com/articles/dfs-strategy/nba-dfs-usage-rate-strategy)
- Stokastic's rules: usage concentrates when one creator remains; same-position overlap through non-overlapping shifts "halves the spike"; redistribution can shift production between categories (one stat down, another up), so price each category separately. — [Stokastic](https://www.stokastic.com/articles/dfs-strategy/nba-dfs-usage-rate-strategy)
- Example on/off figures: Harden's usage approached about 50% with Westbrook off the floor. Frontcourt absences push rebounds to the next big. A co-creator's absence concentrates assists. — [Stokastic research](https://www.stokastic.com/articles/nba-dfs/nba-dfs-research)
- Curry posted a 39.9% usage rate with Durant off the floor, and Isaiah Thomas rose to 33% usage with two teammates off (fantasy analyses, anecdotal). — via search summaries of [FantasyLabs](https://www.fantasylabs.com/?p=75934) and [RotoGrinders CourtIQ](https://rotogrinders.com/articles/nba-starting-five-courtiq-wednesday-march-16th-1219802)
- Role vs skill (1,866 player-seasons since 1978): Usage%, Stl%, TOV% and Blk% are mainly skill (they follow the player). Ast% and rebound percentages, especially DRB%, are strongly role-dependent: when a player takes over another's role, his new Ast%/REB% is better predicted by his predecessor's numbers. — [Neil Paine](https://neilpaine.substack.com/p/which-rate-stats-correlate-more-with); also [Basketball-Reference blog](https://www.basketball-reference.com/blog/index1540.html?p=9776), which cites Phil Birnbaum's finding that rebounding is largely role and position.
- Usage-efficiency tradeoff: Eli Witus's 2008 lineup-based study found that each +1% usage costs about 1.25 points per 100 possessions in efficiency (Dean Oliver's "skill curve" framework). — via search summary citing [Basketball-Reference blog](https://www.basketball-reference.com/blog/indexb433.html?p=8522)
- A low-reliability private spec proposes that only about 60% of a missing player's usage is redistributed, with stat multipliers (points 1.0, assists 0.7, rebounds 0.4). Rebounds go 70% to the direct replacement, 20% to other frontcourt and 10% to guards, and stdev scales with sqrt(minutes ratio). — [edge-assist ruling](https://edge-assist.duckdns.org/data-status/docs/nba-player-props/ruling/NBA%20Player%20Props%20Research%20Pipeline%20Council%20Ruling) (unvalidated; do not adopt parameters without fitting)
- Lineup-level usage is hard to estimate. On-court usages of a lineup's starters summed to 111.5%, which is infeasible, so they must be renormalized (scale by 1/sum). Of 1,287 possible Wizards rotations, only 124 were used in 20 games. The author recommends ridge or Bayesian approaches over plain regression. — [squared2020](https://squared2020.com/2017/12/02/usage-and-efficiency/)

### Inferences
- The role-vs-skill split implies stat-specific redistribution. When a big is out, the replacement's rebound rate should move toward the absent player's (role transfer), not just scale with minutes. When a primary creator is out, assist rate transfers to the next ball-handler. Points or usage shifts are smaller per player and spread across the creators, because usage is mainly a player trait. This is consistent with the unvalidated spec's ordering. That spec has points at 1.0 vs rebounds at 0.4, but its "transfer" is about volume share, not rate, so the two framings differ.
- For the existing model, the biggest misses against book lines are probably cases where a starter or high-minute teammate is ruled Out. The minutes channel (more minutes for the replacement) is likely larger and more reliable than the per-minute usage channel, because books mostly price the minutes bump.
- Efficiency falls as usage rises (Witus), so the points bump from vacated usage is smaller than the FGA bump.

### Gaps
- No published league-wide quantification of, for example, "points per minute rises X% per 10% usage vacated," or of the share of vacated usage absorbed by teammates (vs. lost to pace or efficiency changes). The 60% figure is unsourced.
- Goldman and Rao's Sloan paper on allocative efficiency was not retrieved.

## 3. Estimating with/without effects from box scores alone

### Takeaway
Game-level with/without splits are feasible from box scores plus injury reports, but samples are small, absences are non-random, and opponents differ. Robust approaches estimate effects as team-share reallocations and shrink them heavily toward structural priors (position, role, minutes share). Lineup and on/off data improve it but are not required.

### Cited Findings
- Stokastic calls lineup adjustment "not a perfectly scientific process," and says the goal is a defensible range. It warns against treating extreme on/off samples as noise when roster math makes them real, or as signal when they are not. — [Stokastic](https://www.stokastic.com/articles/nba-dfs/nba-dfs-research); [Stokastic usage](https://www.stokastic.com/articles/dfs-strategy/nba-dfs-usage-rate-strategy)
- Sparse lineup coverage (124 of 1,287 rotations) makes unregularized lineup regression unsuitable; ridge or Bayesian methods are recommended. — [squared2020](https://squared2020.com/2017/12/02/usage-and-efficiency/)
- Season "team usage" vs on-court usage must be adjusted for games played and minutes to recover implied usage, a box-score-only technique. — [squared2020](https://squared2020.com/2017/12/02/usage-and-efficiency/)

### Inferences (suggested implementation, not sourced)
- Model team shares rather than raw splits. For each team-game, compute each player's share of team minutes, FGA+0.44FTA+TOV (usage proxy), REB and AST. Fit a model: share_i,g = baseline_i + sum over absent teammates j of beta(role_i, role_j) + player-specific deviations (shrunk). Pool beta across the league by role pairs (primary ball-handler, wing, big; starter vs bench) so that sparse player-pair samples borrow strength. The empirical-Bayes shrinkage toward the pooled role effect replaces noisy raw with/without splits.
- Define absence from the official injury report and box-score DNPs (Out vs active), not from "didn't play," to avoid leakage. Use the pre-game status as the feature, since that is what is available at bet time.
- Pitfalls:
  - Selection. Absences cluster in back-to-backs, late-season tanking, and blowout-prone games, and stars resting coincides with other teammates resting.
  - Opponent strength. Control with existing opponent factors.
  - Time trends. A player's role grows over a season, confounding "without X" games that occur late.
  - Partial-game absences (player injured mid-game). Exclude games where the absent player logged under about 10 minutes, or code them separately.
  - Multiple simultaneous absences interact non-additively. Cap or renormalize so minutes sum to 240 and shares to 1.
- What lineup or play-by-play data adds: true on/off usage and rebound rates per minute shared (separating "more minutes" from "higher rate"), and substitution patterns. Tracking adds touches and potential assists. Neither is required for a first-order minutes-reallocation model.

### Gaps
- No published robust box-score-only with/without estimator or validation study found.

## 4. Per-minute production stability: regression and recency weighting

### Takeaway
Usage, steal, block and turnover rates are relatively stable player traits. Assist and rebound rates are stable but role-driven, so they should be re-anchored when the role changes rather than simply regressed. No NBA-specific published stabilization points (minutes to r = 0.5) or practitioner half-lives were found, beyond DARKO saying it uses exponential decay and weights recency.

### Cited Findings
- The stabilization method: split-half correlation, finding the sample size where r reaches 0.50 (baseball reference; no NBA numbers found). — [Baseball Prospectus](https://baseballprospectus.com/?p=14215)
- Year-to-year stability ordering: Usage%, Stl%, TOV% and Blk% are more skill-driven; Ast% and REB% (especially DRB%) are role-dependent. — [Neil Paine](https://neilpaine.substack.com/p/which-rate-stats-correlate-more-with)
- DARKO combines daily Kalman-style updating with exponential decay and extra weight on recent play. The decay constants are unpublished. — [Liberty Ballers](https://www.libertyballers.com/2019/12/8/20997234/the-sixers-past-present-and-future); [Power Rank podcast](https://thepowerrank.libsyn.com/kostya-medvedovsky-on-the-darko-nba-player-projections)
- Practitioner blends: 75% season + 25% L5 for minutes (RotoGrinders); 40/30/20/10 L5/L10/L20/season (unvalidated spec). — [RotoGrinders](https://rotogrinders.com/fantasy/lessons/accurately-predicting-minutes-nba-dfs); [edge-assist](https://edge-assist.duckdns.org/data-status/docs/nba-player-props/ruling/NBA%20Player%20Props%20Data%20Audit%20Council%20Ruling)

### Inferences
- Use different half-lives for minutes (role-sensitive, so faster) and per-minute rates (slower; usage especially is a trait). Fit the half-life per stat by minimizing out-of-sample error on 2021-present data rather than adopting any published value. A 3-game half-life on minutes is likely too short, except right after a detected role change.
- Shrink per-minute rates toward a prior that depends on role and position, so role-driven stats (REB, AST) can be re-anchored when the lineup changes.

### Gaps
- No NBA stabilization minute thresholds per stat and no published optimal half-lives.

## 5. Evidence on how much these features improve accuracy

### Takeaway
I found no published MAE or log-loss comparison showing the accuracy gain from minutes-model improvements, teammate-absence adjustments, or blowout adjustments for single-game player projections. Industry sources assert that minutes and injuries are the largest drivers but give no numbers.

### Cited Findings
- RotoGrinders advises comparing third-party sites' past minute projections for accuracy yourself; no published error comparisons. — [RotoGrinders lesson](https://rotogrinders.com/lessons/projecting-minutes-1149307)
- Projected fantasy points are minutes x scoring rate, so minutes errors dominate. — [Stokastic](https://www.stokastic.com/news/using-nba-dfs-projections-in-daily-fantasy-basketball-strategy-ac11)
- Injuries are "the most influential factor" on minutes. — [RotoGrinders](https://rotogrinders.com/fantasy/lessons/accurately-predicting-minutes-nba-dfs)

### Inferences
- The decomposition is testable on the user's own data. Projection error splits into a minutes part and a rate part, roughly: error(stat) ≈ rate x error(minutes) + minutes x error(rate). Computing this split on the existing backtest, especially in games where a top-minutes teammate was Out, would directly measure the value of each feature. If the model's worst disagreements with book lines coincide with teammate-out games, that confirms the missing feature.

### Gaps
- No MAE or log-loss studies on minutes, usage or injury features for single-game NBA projections. No arXiv or Sloan paper on single-game minutes prediction was found; the closest arXiv hit was a team-performance Bayesian network with minutes distributions ([arXiv 2608.09824](https://arxiv.org/pdf/2608.09824)). A GitHub project (AniV729/Detank) lists per-player minutes regression and backup minutes absorption only as roadmap items ([GitHub](https://github.com/AniV729/Detank)).
