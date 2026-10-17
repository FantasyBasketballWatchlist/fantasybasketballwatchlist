# Injuries, Rookies, Team Context, and Forecast Combination in NBA / Fantasy Projection

Research date: 2026-09-29. About 25 tool calls. Source quality varies a lot. Peer-reviewed or institutional sources: the forecasting literature, the ECB SPF paper, the Hyndman et al. review, Armstrong, and Neil Paine's B-Ref study. Student papers and blogs (the injury ML papers, usage-bump betting sites) are labelled as such below.

---

## Q1. Games played / injury projection: how is availability forecast, and how predictable is it?

### Takeaway
Public evidence says that forecasting availability before the season is only moderately possible. The published AUCs that look high (0.80 to 0.87) are for next-game or short-window prediction, and they use features built from very recent absences. They cannot be compared with a preseason "will he lose the season" AUC. BPV's 0.61 to 0.65 from games-played history fits the public evidence, and I found no public study that clearly beats plain history for season-level preseason prediction. Even DARKO says playing time is its weakest area. League policy (the 65-game rule) has had little measurable effect on star availability, because absences are dominated by injury spells.

### Cited Findings
- Next-game injury model (Wharton student paper, Ethan Wang, 2025). Random Forest, 16 workload/recency features, 2010 to 2022, about 140,879 player-game observations, 1,211 players. At a 2% threshold it catches 69% of injuries and correctly rules out 62% of healthy games. The most important features were change in minutes since the last game, average minutes over the last 5 games, days since the last injury, and rest. Age was among the *least* predictive. — [Wang, Wharton (PDF)](https://wsb.wharton.upenn.edu/wp-content/uploads/2025/12/WANG_Using-Injury-Risk-Forecasting-to-Quantify-Financial-Impact-in-the-NBA-1.pdf)
- The same paper cites earlier work reporting ROC AUC 0.80 for NBA injury prediction. — [Wang (PDF)](https://wsb.wharton.upenn.edu/wp-content/uploads/2025/12/WANG_Using-Injury-Risk-Forecasting-to-Quantify-Financial-Impact-in-the-NBA-1.pdf)
- Availability model (University of Rochester course project, 2025). Each player-season is an 82-bit played/missed vector with sliding windows of 5 to 41 games; 5 to 10 games was best. Features include `zero_maxrun` (longest streak of games missed) and `bit_sum` (games played). Reported AUCs: logistic regression about 0.73, Random Forest about 0.79, LGBM about 0.83, MLP about 0.77. Taller, heavier players showed higher risk. — [McClung, Rochester (PDF)](https://hajim.rochester.edu/ece/sites/zduan/teaching/ece408/projects/2025/MaxMcClung_NBAInjuryRiskAndAvailabilityAnalysis_FinalReport.pdf)
- "INJURYx" blog: season-level XGBoost with AUC about 0.87 and recall about 0.76. The target definition and whether features were lagged could not be verified (403 on fetch). The search summary also reports per-game AUC of about 0.67 to 0.70. — [Medium/INJURYx](https://medium.com/@chrismylp1/injuryx-can-we-predict-nba-injuries-with-only-public-data-f44e47375845)
- Deep-learning injury forecasting (Journal of Sports Analytics, 2020): ROC AUC 0.77 to 0.87 depending on body area (back 0.87). — [JSA 2020](https://journals.sagepub.com/doi/10.3233/JSA-200529)
- Schedule effects: back-to-backs and away games were significant predictors of game injuries (J Sci Med Sport). — [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S1440244016301633)
- DARKO, the leading public NBA projection system, forecasts minutes "based on recent playing time and role." It says: "the only stat where DARKO lost was in minutes projections. Predictably, playing-time projections are the hardest part of any projection system." The About page does not describe how injuries are handled. — [DARKO About](https://www.darko.app/about)
- 65-game rule (from 2023-24): Adam Silver reported about 15% fewer games missed by stars in year 1. — [Hoops Rumors / search summary](https://www.hoopsrumors.com/2024/03/hoops-rumors-glossary-65-game-rule.html); [Sportico 2024](https://www.sportico.com/leagues/basketball/2024/nba-awards-load-management-adam-silver-1234775529/). In 2024-25, the share of back-to-backs where a star played one game but not the other *rose* from 22% to 24%. — [Sportico 2025](https://www.sportico.com/leagues/basketball/2025/nba-injuries-load-management-data-participation-1234849899/) (the figure is from the search snippet; the full page could not be fetched)
- Independent analysis of the 65-game rule, covering 2013-14 to 2025-26 (excluding 2019-20 and 2020-21), all player-games. It found no bunching at 65 games, no change in how often stars cross the threshold, and no star-specific effect compared with controls. About half of the league's reported rise in star games came from redefining who counts as a star. Only 25 to 40% of stars are within reach of the threshold late in a season. Star absence is "dominated by injury spells the rule does not touch." — [L-Maddock/nba-65-game-rule (GitHub)](https://github.com/L-Maddock/nba-65-game-rule)

### Inferences
- The AUCs of 0.80 to 0.87 are not a benchmark BPV is failing to reach. They come from different targets (next game or next few games) and use features like current missed-game streaks, which mostly capture "already injured, still out." Preseason season-level AUCs around 0.6 to 0.65 are probably close to the ceiling with public data. This is inferred: no clean public preseason benchmark was found.
- The next-game feature-importance results (workload change, recent minutes, days since last injury, age weak) support BPV's finding that 23 proneness signals add little beyond games-played history. The remaining information is mostly news (offseason surgery, recovery timelines), not box-score history. That explains why ESPN projected games (scaled by 0.86) helps: ESPN's GP number carries news. It also suggests some of ECR's edge is timing and news, not modelling skill.
- Treat games played as a heavily regressed quantity. Use a multi-year GP history shrunk toward a league prior by age and minutes, then overwrite with known preseason news (surgery, timelines). Do not add more proneness features.
- The 65-game rule should not be modelled as a structural break in star availability. The best independent evidence finds no effect.

### Gaps
- No peer-reviewed, preseason, season-level public benchmark for "games missed" R² or AUC was found. No published R² for year-to-year NBA games played was found.
- No public documentation was found of how ESPN, FantasyPros experts, or Hashtag Basketball turn injury news into projected GP.
- The INJURYx 0.87 season-level AUC could not be verified. It should be assumed to leak (same-season features) until shown otherwise.

---

## Q2. Rookie and draft-prospect projection

### Takeaway
The best public rookie projections blend a statistical translation (college, international, or EYBL stats translated to NBA equivalents and adjusted for age) with scouting consensus or draft slot. Pelton explicitly finds that adding consensus/draft slot improves projections. DARKO's rookie prior uses only age, draft slot, and height, then learns fast. Summer league adds only weak signal (r about 0.20). For a fantasy model, the practical approach is a draft-slot × age × height prior, blended with outside projections (ESPN, ECR) that already contain scouting information.

### Cited Findings
- Pelton's (ESPN) draft projections have three inputs: projected rookie performance from translated stats, age, and the prospect's rank in ESPN's consensus top 100. He translates 14 core rate stats (2P%, 3P%, FT%, OREB%/DREB%, AST/STL/fouls per 100 team plays, blocks per 100 opponent 2PA, shot-type shares, TOV, usage), adjusted for strength of schedule. "Free throw percentage rarely changes much, but players shoot much worse percentages from the field." Outlier stats are regressed toward positional averages; one prospect shot 56.8% from three in college and 29.9% in the NBA. "Using the actual draft slot plays a factor in subjective scouting analysis and improves projections," so the consensus-blended version is his main ranking. The database runs mostly from the 2006 draft (some players back to 2003). The page gives no explicit accuracy correlations. — [ESPN, Pelton explainer](https://www.espn.com/nba/story/_/id/16235135/explaining-kevin-pelton-nba-draft-projection-system)
- DARKO rookie prior: before a player's first NBA game, the projection comes from "age, draft slot and height," and learning is rapid early in a career. Example: 2025 No. 1 pick Cooper Flagg started at −0.7 DPM. When a player changes teams, DARKO raises its learning rate. — [DARKO About](https://www.darko.app/about)
- Summer league (Pelton, ESPN mailbag): rookie summer-league performance correlates about 0.20 with the regular season, compared with about 0.30 for his pre-draft projections. For veterans it is about 0.26, over 12 years of data. Rebounding, assist rate, and block rate translate. Shooting percentages have "little predictive power." Steal and turnover rates are "somewhat misleading." — [ESPN Pelton mailbag](https://www.espn.com/espn/print?id=20122364). A search snippet attributes different numbers (r = .463 for summer league compared with .468 for college translations) to an unidentified analysis. It is **unverified and conflicts** with the ESPN numbers above.
- Peer-reviewed study (Journal of Sports Economics, 2006 to 2019 data): summer-league scoring beyond what was expected predicts rookie scoring, even after controlling for draft position. — [SAGE abstract](https://journals.sagepub.com/doi/abs/10.1177/1527002520959138)
- Draft-slot value curves: value falls steeply from pick 1 to pick 10 (drafts 1979 to 2015, PER/Win Shares over 5 prime years) — [U. Arizona thesis](https://repository.arizona.edu/bitstream/handle/10150/651330/azu_etd_hr_2020_0130_sip1_m.pdf). The 5th pick averages about 46.6 career WS and about 16.4 WS in the first four seasons; the average 3rd pick produces about 10 wins over the rookie deal. — [B-Ref blog](https://www.basketball-reference.com/blog/index616a.html?p=2740); [The Ringer](https://www.theringer.com/2021/07/28/nba-draft/nba-draft-expectations)

### Inferences
- For fantasy points per game in year 1, the main uncertainty is minutes and role, not talent. A draft-slot × age prior for minutes and per-minute production is the defensible baseline you can reproduce from draft history plus game logs. ESPN projections and ECR already include scouting and depth-chart information, so for rookies they should get *more* weight than for veterans. This could be a slice-specific weight: one extra parameter, which is reasonable even with 4 to 5 seasons.
- Second-year players: DARKO-style fast early learning suggests weighting year-1 NBA data heavily but regressing toward the draft prior, since one rookie season is a small sample. No public quantitative source was found on second-year jumps specifically.

### Gaps
- No published accuracy figures (RMSE or correlation against realised fantasy production) were found for rookie fantasy projections from ESPN, FantasyPros, or others.
- No quantitative evidence was found on second-year ("sophomore leap") projection adjustments.
- No public college-to-NBA translation factors were found in a form that can be reused directly (Pelton's are proprietary).

---

## Q3. Team context: usage redistribution, pace, coaching, trades

### Takeaway
Rate stats transfer across teams unevenly. Neil Paine's study shows shooting efficiency is the most disrupted by a team change, while rebounding and assist rate are stable, with assists depending on role. Usage does rise when a high-usage teammate is out, but efficiency falls: roughly −0.6 to −1.25 points per 100 possessions for each +1% of usage, and the drop is larger for low-usage players. Public "usage bump" numbers mostly come from betting blogs and should be treated as unverified. DARKO handles team changes by increasing uncertainty, through a higher learning rate, rather than by applying explicit context adjustments.

### Cited Findings
- Neil Paine (Basketball-Reference, Dec 2010): players aged 24 to 34 with 1,000+ minutes in back-to-back seasons, 1974 to 2010. Year-to-year correlations for no change / changed team only / changed role only / changed team and role:
  - TS%: 0.706 / 0.556 / 0.686 / 0.593
  - ORtg: 0.719 / 0.563 / 0.695 / 0.617
  - Assist rate: 0.974 / 0.963 / 0.875 / 0.792
  - TOV rate: 0.802 / 0.735 / 0.756 / 0.715
  - FT rate: 0.842 / 0.811 / 0.828 / 0.742
  - OREB%: 0.944 / 0.930 / 0.943 / 0.924

  Shooting efficiency "is actually far more impacted when a player changes teams than when he changes roles." — [B-Ref blog, Paine](https://www.basketball-reference.com/blog/index0597.html?p=8472)
- Usage-efficiency tradeoff: Dean Oliver (2005) estimated about 0.6 points per 100 possessions per 1% of usage. Eli Witus (2008, lineup data, which avoids the chicken-and-egg problem) estimated about 1.25 points per 100 per +1% usage, in a league with ORtg 107.5. The effect is larger for low-usage players, about twice as large (Hoiberg vs. Garnett example). — [APBRmetrics / search summary](https://apbr.org/metrics/viewtopic.php?t=8861); [B-Ref blog, Optimizing the '95 Rockets](https://www.basketball-reference.com/blog/index9e74.html?p=5500). There is also a caveat that "the skill curve remains a highly theoretical object that has never been extracted from data in a generally accepted way." — [arXiv 1912.05129](https://arxiv.org/pdf/1912.05129)
- Betting and fantasy blogs (low quality, no methodology) claim that when a 32%-usage star sits, a secondary creator gains +3 to 5 usage points, a secondary scorer +2 to 3, and bench players +1 to 2 each, while efficiency falls. — [nbaplayerbets](https://nbaplayerbets.com/articles/nba-usage-rate-prop-betting/); [NBAstuffer](https://www.nbastuffer.com/what-changes-when-star-teammate-out/). These are unverified heuristics.
- DARKO on team changes: it "accounts for" free agency by becoming "less confident in its understanding of a player's talent when they change teams, effectively increasing its 'learning rate.'" Opponent, rest, travel, and home court are adjusted daily. — [DARKO About](https://www.darko.app/about)
- DFS-style pace adjustments: the per-minute rate is multiplied by projected minutes, then by a pace factor (both teams' pace relative to league average), clamped to ±5% in one described system. — [search summary of fantasy projection sites; e.g. RotoGrinders](https://rotogrinders.com/fantasy/lessons/nba-player-projections)

### Inferences
- For ESPN points leagues (volume-driven), the main team-context effect is **minutes and usage volume**. A usage gain is partly offset by lower efficiency, but fantasy points reward volume (FGA, AST, REB) more than efficiency, so net FPTS likely rise when a high-usage teammate leaves. This is inference, not measured.
- In our model, team change could be a variance or shrinkage flag rather than a point adjustment: regress traded or free-agent players more heavily toward priors and toward external projections, as DARKO does. ESPN and ECR already price in depth-chart news, so this is another slice where outside sources should get more weight.
- Paine's table suggests keeping rebound and assist rates from history even after a team change, but regressing shooting percentages harder.

### Gaps
- No rigorous public study was found that measures how much of a departed player's usage or FPTS moves to specific teammates (for example, a "with or without you" meta-analysis). The quantitative figures available are betting-blog heuristics.
- No quantitative evidence was found on how new coaches affect player stats or team pace.
- No public accuracy comparison was found between projections with and without team-context adjustments.

---

## Q4. Forecast combination: averaging, optimal weights, stacking, and combining rankings

### Takeaway
There is strong and consistent evidence that combining forecasts beats most individual forecasters. Armstrong found an average error reduction of about 12.5% across 30 comparisons. In M4, 12 of the 17 best methods were combinations. The simple equal-weight average is very hard to beat with estimated weights (the "forecast combination puzzle"), because weight-estimation error cancels out the theoretical gains, especially over short histories. With 4 to 5 seasons, the evidence-based recommendation is equal weights, or weights heavily shrunk toward equal, with at most one or two free parameters. Any "winning" weight should be treated as possibly produced by chance. For rankings, convert each source's rank to a value on a rank-to-value curve, average the values, then re-rank. FantasyPros evaluates accuracy this way too.

### Cited Findings
**General forecasting literature**
- Armstrong (Principles of Forecasting): in 30 empirical comparisons, equal-weight combined forecasts cut ex-ante errors by about 12.5% on average (range 3 to 24%). The principles are: combine methods that differ substantially and use different information; use equal weights unless there is strong evidence for unequal weighting; use a trimmed mean when combining five or more methods. Combining helps most when you are unsure which method is best. — [Armstrong, Combining Forecasts (PDF)](https://faculty.wharton.upenn.edu/wp-content/uploads/2001/01/96-JSA-Combining-Forecasts.pdf)
- Wang, Hyndman, Li & Kang (2022), a 50-year review:
  - The simple average is "the most popular and surprisingly robust combination rule."
  - In the original M-competition (1,001 series; Makridakis et al. 1982) the simple average beat the individual models.
  - Clemen (1989) reviewed early work and raised the question of why arithmetic means often beat refined combinations.
  - Stock & Watson (2004) named the "forecast combination puzzle."
  - Timmermann (2006) and Smith & Wallis (2009) explain it as weight-estimation error. Smith & Wallis show the cost of estimating weights when the optimal weights are close to equal.
  - Claeskens et al. (2016) show that estimated weights can add bias and variance.
  - Elliott (2011) shows the possible gains from optimal weights are often too small to offset estimation error.
  - Blanc & Setzer (2020) frame the choice as a bias-variance tradeoff.
  - Remedies: Bates & Granger (1969) inverse-MSE weights that ignore correlations; Diebold & Shin (2019) LASSO selection followed by shrinking survivors' weights toward equal; clustering forecasters (Aiolfi & Timmermann 2006); median and trimmed means for robustness.
  - Stacking (Wolpert 1992) is covered as an option but needs enough data.

  — [Wang et al., arXiv 2205.04216](https://arxiv.org/pdf/2205.04216)
- Genre, Kenny, Meyler & Timmermann (IJF 2013, ECB SPF). They tested principal components, trimmed means, performance-based weights, OLS optimal weights, and Bayesian shrinkage. For GDP and unemployment, "only few" schemes beat the equal-weight average. Inflation showed stronger gains because the equal-weight average had a *persistent downward bias* that flexible schemes could correct. After White's reality check for multiple comparisons, the improvements were generally not statistically significant, and the best method changed with variable and horizon. Their conclusion: "only a very modest case" for anything other than equal weights, and caution "strongly against any temptation to try and pick out a preferred or best combination method." — [Genre et al. (PDF)](https://rady.ucsd.edu/_files/faculty-research/timmermann/SPF_IJoF_2012_06_22.pdf)
- M4 (100,000 series, 61 methods): the simple Comb benchmark (average of SES, Holt, and Damped) scored sMAPE 12.55%, better than each component (13.09 / 13.77 / 12.66). 12 of the 17 most accurate methods were combinations. The best hybrid improved about 9.4 to 10% on Comb, and the top 16 averaged about 4.5% better. — [M4 results (ResearchGate)](https://www.researchgate.net/publication/325901666_The_M4_Competition_Results_findings_conclusion_and_way_forward)
- Good Judgment Project (probability forecasts): weighted and extremized aggregation beat the unweighted mean. In one reported case, extremizing improved Brier from 0.173 to 0.161, and 0.158 with hindsight-optimized extremizing. Weights favored forecasters with good track records who updated often. — [AI Impacts summary](https://aiimpacts.org/evidence-on-good-forecasting-practices-from-the-good-judgment-project/); [Wharton, Crowd Prediction Systems](https://faculty.wharton.upenn.edu/wp-content/uploads/2016/11/Crowd-Prediction-Systems.pdf). This applies to binary probabilities from hundreds of forecasters on thousands of questions, not to point projections from 2 or 3 sources.

**Sports projections**
- Baseball, 2014 (THT/FanGraphs): wOBA MAE weighted by plate appearances, 177,967 PA. ZiPS 0.0274, Steamer 0.0277, PECOTA 0.0279, Oliver 0.0280, Marcel 0.0289. **The average of systems was 0.0270, better than every individual system**, although it was computed only on players projected by all systems. Marcel, the simplest system, is only modestly worse. — [THT, Evaluating the 2014 Projection Systems](https://tht.fangraphs.com/evaluating-the-2014-projection-systems/)
- FanGraphs Depth Charts is a 50/50 blend of Steamer and ZiPS, prorated to RosterResource playing-time projections. That is equal weights for rates, with playing time handled separately. "Composite projection systems like this tend to do better when tested against actual player performance." — [FanGraphs Library, Projection Systems](https://library.fangraphs.com/principles/projections/)
- FanGraphs game-theory comparisons (2019 to 2023) rank the best system differently each year: in 2023 ATC (itself a weighted average) had the best top-50 hit rate, while Steamer was best for picks 1 to 100. — [FanGraphs 2023 comparison](https://fantasy.fangraphs.com/2023-projection-systems-comparison-a-game-theory-approach/)
- FantasyPros (fantasy football, 2010, 40+ experts): a top-5 consensus scored 61.6% on PAY accuracy, the best individual (Paulsen) 61.3%, and the all-expert consensus 60.5%. The all-expert consensus finished top 10 at all four positions. — [FantasyPros, ECR accuracy](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/). Consensus of the top 5 experts would have been beaten by only 2 individual experts, and was more accurate than any individual over the last 4 weeks. — [same](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)

**Combining rankings (not projections)**
- FantasyPros ECR assigns "Rank Points" by each expert's rank position and sums them across experts. — [FantasyPros tools FAQ](https://www.fantasypros.com/tools/); [ECR support](https://support.fantasypros.com/hc/en-us/articles/115001219327-What-is-ECR-Expert-Consensus-Rankings-and-how-do-you-calculate-it)
- Averaging raw ranks "treats the gap between 1st and 10th the same as between 200th and 210th." Instead, convert each rank to a value on an exponential decay curve, average the values, and re-rank. DynastyProcess converts FantasyPros ECR to values this way. — [DynastyProcess values](https://dynastyprocess.com/values/)
- Borda count is the standard rank-aggregation method, and Kendall's W can measure how much raters agree. — [MetricGate](https://metricgate.com/docs/borda-kendall-rank-aggregation/)

### Inferences (applied to BPV + ESPN + ECR)
1. **Put everything on one scale before combining.** Map ECR rank to expected FPTS/game using a curve fitted on *past seasons only*. For example, for each season fit realised FPTS/G against ECR rank, then average the curves across seasons with isotonic or exponential smoothing. That turns ECR into a projection you can blend with BPV and ESPN. FantasyPros scores experts the same way (rank slot → points from a rolling 3-year average, see Q5).
2. **Default to equal weights (1/3 each), or shrink toward equal.** With 4 to 5 seasons, and errors from the same players correlated across seasons, the effective sample for choosing weights is small. The puzzle literature (Smith & Wallis; Genre et al.) predicts that the "optimal" 62.5/37.5 BPV/ESPN weight is partly noise. A defensible rule: w = λ·w_est + (1−λ)·equal, with λ ≤ 0.5, and choose it with leave-one-season-out CV.
3. **ECR beating the blend by about 0.3 FPTS/G is a bias and information-timing signal**, like inflation in the ECB paper, where flexible combinations helped because the average was biased. Check whether the gap comes from specific slices: rookies, team changers, and injury-news players, where ECR and ESPN include news. If so, use slice-specific weights (one parameter per slice, few slices) rather than one global weight.
4. **Combine sources that differ.** BPV (statistical) with ECR (human, news-driven) are the most complementary pair. ESPN is partly both. Armstrong's rule suggests including all three rather than dropping the weakest.
5. **Guard against the "best method was luck" problem.** Compare candidate weightings with a paired test on per-player errors clustered by player (Diebold-Mariano style, or White's reality check / SPA if many weightings are tried). Pre-register a small grid, for example {BPV-only, equal-3, 0.25/0.25/0.5 ECR-heavy}, instead of fine-grained optimisation.
6. **Extremizing** (GJP) applies to probabilities such as P(player misses 20+ games), not to FPTS projections.

### Gaps
- No NBA-specific published study was found comparing a stats model, ESPN projections, and ECR, or an average of them. The 0.3 FPTS/G result appears to be the only such evidence (our own).
- No public quantitative evaluation of FantasyPros NBA (basketball) accuracy was found; the evidence is football (2010) and baseball.
- The shape of the NBA rank-to-FPTS curve is not published. It must be fitted from our own data.

---

## Q5. Accuracy measurement: metrics and pitfalls

### Takeaway
Projection evaluations use (a) MAE or RMSE on rate stats, weighted by playing time; (b) correlation or R² after adjusting to a common league mean; (c) for rankings, rank-slot→points "accuracy gaps"; and (d) decision-based tests such as draft or auction simulations. The main pitfalls: which players are included (survivorship/selection), comparing different player sets across systems, hindsight-snapshot timing, and repeatedly testing many methods on the same few seasons.

### Cited Findings
- FantasyPros draft-accuracy method:
  - Snapshot of each expert's rankings just before week 1.
  - Player pool = preseason ECR-relevant players ∪ the season's actual fantasy leaders, which catches surprise studs and busts.
  - Each rank is turned into projected points from the historical (rolling 3-year average) production of that rank slot, then compared with actual points to give an "Accuracy Gap."

  — [FantasyPros accuracy methodology (search summary of FAQ pages)](https://www.fantasypros.com/about/faq/football-draft-accuracy-methodology/); [baseball method](https://support.fantasypros.com/hc/en-us/articles/115002308108-How-do-you-measure-the-accuracy-of-fantasy-baseball-experts?mobile_site=false)
- THT 2014 evaluation:
  - MAE weighted by plate appearances, with each system adjusted to a common league mean (0.315 wOBA).
  - Also reported R² (ZiPS 0.330 … Marcel 0.240) and projection spread (SD).
  - Coverage differed a lot: Marcel left 11.7% of PA unprojected against about 1 to 3% for other systems.
  - The average-of-systems comparison used only players projected by all systems.

  — [THT 2014](https://tht.fangraphs.com/evaluating-the-2014-projection-systems/)
- FanGraphs "game theory" comparisons measure decision value: whether players a system is higher on than the market (ADP) return a profit. — [FanGraphs 2023](https://fantasy.fangraphs.com/2023-projection-systems-comparison-a-game-theory-approach/)
- The multiple-comparisons pitfall: Genre et al. used White's (2000) reality check because they tested many combinations on one dataset, and the apparent winners mostly stopped being significant. — [Genre et al.](https://rady.ucsd.edu/_files/faculty-research/timmermann/SPF_IJoF_2012_06_22.pdf)
- DARKO reports accuracy against DFS projections stat by stat. There is an internal inconsistency on minutes: one line lists minutes among stats where it "outperformed," while another says minutes was "the only stat where DARKO lost." — [DARKO About](https://www.darko.app/about)

### Inferences
- For BPV vs ESPN vs ECR, evaluate on a **fixed, pre-declared player pool** that is the same for all sources. Use the union of top-N by each source's preseason rank and top-N by actual season value, like FantasyPros. Players who got hurt stay in: restricting to players who played enough games is survivorship bias that helps whichever source ignored injury risk.
- Report two targets separately: FPTS/G (the rate, conditional on playing) and season total FPTS (rate × GP). Combining weights can differ between them. In the Depth Charts approach, rates are averaged and playing time is handled by a separate layer.
- Use timestamped snapshots: ECR and ESPN taken at the same date as BPV's inputs. Otherwise ECR's advantage may just be later news (a hindsight or timing advantage).
- Use rank correlation (Spearman) over the draftable pool as a secondary metric, because draft decisions depend on ordering. A draft-simulation value metric is the most decision-relevant.

### Gaps
- No public NBA-specific projection accuracy benchmark (RMSE on FPTS/G by system) was found.
- The FantasyPros basketball-specific methodology page was not retrieved; the football and baseball versions are assumed to be similar.
