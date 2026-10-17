# How Commercial/Public Fantasy Basketball Projection & Ranking Sources Work, and Evidence on Their Accuracy

Research date: 2026-09-29. About 20 tool calls. Several primary pages (FantasyPros support center, ResearchGate, Springer full text) returned 403/redirects, so some claims rest on search-engine snippets of those pages; these are flagged.

## Q1. ESPN projections and ESPN analyst rankings: who makes them, method, injuries/games played

### Takeaway
ESPN's public fantasy basketball projection articles are written by named analysts (mainly Andre Snellings for projections/rankings in 2022-2026). ESPN publishes no methodology document: there is no public model description, no minutes-assumption table, and no accuracy record. "Mike Clay-style" model documentation exists for ESPN NFL, not NBA, as far as I could find.

### Cited Findings
- ESPN's rest-of-season points/H2H projections for 2024-25 are authored by Andre Snellings ("senior writer for men's and women's fantasy basketball and sports betting at ESPN"). Players are "ranked for their expected performance from Dec. 10 forward", which means the projections are periodically re-dated rest-of-season snapshots. The article has no methodology text. — [ESPN, 2024-25 ROS projections](https://www.espn.com/fantasy/basketball/story/_/id/42898411/fantasy-basketball-rankings-projections-points-h2h)
- Snellings holds a Ph.D. in biomedical engineering, joined ESPN in 2017 and was previously a RotoWire writer/analyst. His projections are described as "inclusive of games played so far" (i.e., season totals combine actuals with the remaining projection). — [ESPN Snellings Ultimate Draft Board (2022)](https://www.espn.com/fantasy/basketball/story/_/id/34732411/fantasy-basketball-andre-snellings-ultimate-draft-board-nba); search summary of ESPN articles
- ESPN also publishes points-league cheat sheets and draft kits with rankings and a schedule grid (2025-26), showing that games-played and schedule considerations are part of the product. — [ESPN cheat sheet 2025-26](https://www.espn.com/fantasy/basketball/story/_/id/46539070/fantasy-basketball-cheat-sheet-2025-26-nba-player-rankings-schedule-grid)
- The only "methodology" descriptions I found for ESPN projections (e.g., "minutes played, player roles, team pace, and even player health") came from low-quality SEO/content-farm pages (rubycom.espaillatcabral.com). They are **not reliable** and should not be cited as ESPN's method. — [example SEO page](https://rubycom.espaillatcabral.com/public-insights/espn-fantasy-basketball-projections-your-winning-guide-1764815394)

### Inferences
- ESPN's in-game default projections (the numbers shown in the ESPN league UI) probably come from a different pipeline, possibly a data vendor plus analyst adjustment, than the analyst articles. Nothing public confirms this either way.
- ESPN's analysts rank for ESPN default points scoring, which is the same target as BPV. Their rankings already bake in games-played and availability expectations, while a per-game stats formula does not.

### Gaps
- No public ESPN NBA projection methodology, minutes model, injury/games-played rule or accuracy record was found.
- Whether the ESPN in-app default projections equal Snellings' article projections is unknown.

## Q2. FantasyPros ECR: construction, accuracy contests, how much top experts beat consensus, persistence

### Takeaway
ECR aggregates rankings from many outlets (40+ listed for NBA) using a "Rank Points" sum rather than a simple average. It shows best/worst/avg rank and standard deviation. FantasyPros' published accuracy contests and methodology are documented for NFL (and MLB), and I found **no published NBA accuracy leaderboard**. The only direct consensus-vs-expert numbers are NFL: ECR finished #2 of 40+ experts in 2010, and a top-5 consensus beat every individual expert.

### Cited Findings
- **ECR construction:** "FantasyPros adds Rank Points up for each player across all experts to determine the player's consensus rank. They don't use an 'average rank' because… using an average requires assigning an arbitrary rank to unranked players." ECR also displays each player's Best Rank, Worst Rank, Average and Standard Deviation, and a lower SD means more agreement. (The primary support page returned 403; this is quoted from its search snippet.) — [FantasyPros support: What is ECR](https://support.fantasypros.com/hc/en-us/articles/115001219327-What-is-ECR-Expert-Consensus-Rankings-and-how-do-you-calculate-it); [FantasyPros high-SD article (MLB 2023)](https://www.fantasypros.com/2023/03/players-high-standard-deviations-rankings-2023-fantasy-baseball/)
- **NBA expert pool:** the NBA expert directory lists 40+ outlets, including Yahoo! Sports, CBS Sports, RotoWire, FantasyPros, Footballguys, 4for4, The Deep Shot, USA Today and Sporting News, plus names such as Scott Pianowski, Andy Behrens, Dalton Del Don, Chris Towers and Pat Fitzmaurice. No accuracy scores are shown on the NBA page. — [FantasyPros NBA experts](https://www.fantasypros.com/experts/nba/)
- FantasyPros publishes ECR variants for ESPN points leagues (overall and rest-of-season) as well as dynasty. — [ECR ESPN points](https://www.fantasypros.com/nba/rankings/overall-points-espn.php); [ROS ESPN points](https://www.fantasypros.com/nba/rankings/ros-overall-points-espn.php)
- **Accuracy methodology (NFL-documented):** each rank slot is converted into projected points equal to what that rank slot actually produced. The "Accuracy Gap" is |projected points − actual points| per player, summed. Unranked players get a rank "1 spot lower than the lowest ranking the player received across experts." Preseason (draft) accuracy has been tracked since 2010 and in-season since 2009. The older PAY metric was replaced. — [FantasyPros accuracy FAQ](https://www.fantasypros.com/accuracy/)
- The player pool is the "Top X in ECR and the Top X in Actual Fantasy Points," and ECR itself is not an entrant in the contest. Penalties apply only where an expert notably underperforms the average expert on a player. — [FantasyPros NFL in-season methodology](https://www.fantasypros.com/about/faq/football-inseason-accuracy-methodology/)
- **Consensus vs experts (NFL 2010 in-season):** the consensus of all 40+ experts scored 60.5% accuracy and ranked #2 overall. The 2010 Top-5-expert consensus scored 61.6%, the highest of any entry, above the best individual (John Paulsen, 61.3%). The rolling Top-5 consensus scored 60.4%. FantasyPros' conclusion: "consolidated recommendations help to reduce the negative impact of outlier predictions." — [FantasyPros, Jan 2011](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)
- The same NFL study reports that consensus was ~10th best over the first 4 weeks but more accurate than every individual over the final 4 weeks (search snippet of the same article). — [FantasyPros, Jan 2011](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)
- **Persistence (NFL):** FantasyPros keeps multi-year (rolling 3-year) accuracy leaderboards. Some experts show repeated top finishes: John Paulsen was top-10 in 10 of 12 seasons and Justin Boone had nine top-10 in-season finishes over 12 years. These claims come from vendor and self-promotional pages. — [FantasyPros multi-year draft accuracy](https://www.fantasypros.com/nfl/accuracy/multi-year-draft.php); [DraftSharks KB](https://www.draftsharks.com/kb/most-accurate-fantasy-football-experts); [4for4 accuracy](https://www.4for4.com/4for4-fantasy-football-accuracy)
- Razzball has criticized the FantasyPros weekly NFL contest for incentivizing boldness, i.e., how it rewards deviating from consensus. — [Razzball football](https://football.razzball.com/the-fantasypros-weekly-nfl-rankings-and-incentivizing-boldness/)

### Inferences
- Averaging many semi-independent rankers cancels idiosyncratic errors (outlier opinions on individual players). This is the standard forecast-combination result. The NFL numbers show that a consensus is roughly as good as the single best expert, whom you cannot identify in advance.
- Rank-based ECR converts to value through "what that rank slot actually produced." A consensus rank therefore implicitly includes games-played and availability risk, which a per-game stats model does not. This is a plausible part of the ~0.3 FP/G gap BPV observed, especially if the BPV evaluation compared per-game projections against realized value that includes missed games or role changes.
- Repeated top-10 finishes out of ~100+ experts suggest some persistence, but no formal year-over-year correlation was published. Survivorship and selective self-promotion are real risks.

### Gaps
- No FantasyPros NBA accuracy methodology or NBA accuracy leaderboard was found. It is unclear whether FantasyPros runs one for NBA at all. I could not establish how much the best NBA experts beat NBA ECR.
- The exact Rank Points formula (e.g., points = N − rank + 1 or similar) and whether experts are weighted by accuracy or recency could not be read (403 on the support page).
- No formal year-to-year correlation of expert accuracy was found for any sport.

## Q3. Other sources: Basketball Monster, Hashtag Basketball, RotoWire, Yahoo, CBS, Fantrax, NumberFire, Razzball, SportsLine

### Takeaway
The public descriptions share one architecture: **projected minutes × per-minute rates, with games-played/injury adjustments and continuous news-driven updates, then z-score (category) or fantasy-point valuation**. All the named projections are human-maintained or human-reviewed. None of these sites publish accuracy numbers.

### Cited Findings
- **Basketball Monster:** the main projection set is maintained by Josh Lloyd ("Josh Projections"), with an alternative "Bonus Projections" set (the latter reportedly Kyle McKeown's). Full-season projections "refresh several times a day"; daily/short-term projections "refresh as soon as news happens, and cover the next three weeks." Valuation uses z-scores ("0.00 is your league average, 3 or higher is very good"), and the site also has a "Value30" per-game value assuming 30+ minutes. The help page makes no accuracy claims. — [Basketball Monster Help/FAQ](https://basketballmonster.com/Help.aspx)
- Basketball Monster's team minutes intentionally sum above 240 because they project season totals with a 5-10% overage for injuries/unknowns (from the search summary of BBM pages). — [BBM Welcome 2025/26](https://basketballmonster.com/article.aspx?article=2185); [BBM Help](https://basketballmonster.com/Help.aspx)
- **Hashtag Basketball:** offers long- and short-term projections plus ROS rankings with z-score valuation and toggleable categories. It also offers BLEND7/BLEND14 sets that are 50/50 blends of the site's projection with the player's last-7/14-day averages. There is a separate points-league projection page. No accuracy claims were found. — [Hashtag projections](https://hashtagbasketball.com/fantasy-basketball-projections); [Hashtag points projections](https://hashtagbasketball.com/fantasy-basketball-points-league-projections)
- **RotoWire:** uses "statistical models that combine historical performance, projected minutes, team pace, and matchup data," weighted by predictive reliability ("minutes matter far more than a single game's shooting percentage"). Daily projections are "reviewed by expert analysts" for "coaching tendencies, injury recovery timelines, and lineup changes." Projections "adjust immediately" when the injury report updates or starting lineups are confirmed. RotoWire describes them as "generally reliable but not perfect" and gives no numbers. — [RotoWire NBA projections](https://www.rotowire.com/basketball/projections.php)
- **General industry framework (DFS-oriented):** projections reduce to "1) Playing Time (minutes) 2) Efficiency (points per minute)," plus pace. — [RotoGrinders, NBA projections foundational knowledge](https://rotogrinders.com/fantasy/lessons/nba-player-projections); [RotoGrinders key inputs](https://rotogrinders.com/lessons/key-inputs-in-an-nba-projections-system-1144825)
- Yahoo and CBS experts (Pianowski, Behrens, Del Don, Towers, etc.) appear as ECR contributors. — [FantasyPros NBA experts](https://www.fantasypros.com/experts/nba/)

### Inferences
- The shared emphasis on minutes and news speed suggests that the main edge over a stats-only formula is the **minutes/role/availability term**, not the per-minute rate term.
- Hashtag's BLEND7/14 is an explicit admission that recent form carries information beyond the base projection, likely role or minutes changes that appear in recent box scores before the base projection is updated.

### Gaps
- No public methodology or accuracy evidence was found for Yahoo, CBS, Fantrax, NumberFire/FanDuel Research, Razzball NBA or SportsLine NBA projections within the call budget. Their methods are unknown (not searched in depth).

## Q4. Independent accuracy comparisons and wisdom-of-crowds evidence

### Takeaway
Only one peer-reviewed NBA-specific study turned up: Döpke, Köhler & Tegtmeier (2024), covering daily/DFS projections. It found that professional projections beat naive past-performance forecasts only moderately, and that providers differ only slightly in the long run. I found no Reddit or blog study comparing season-long fantasy basketball projection accuracy.

### Cited Findings
- Döpke, Köhler & Tegtmeier, "Are they worth it? – An evaluation of predictions for NBA 'Fantasy Sports'," *Journal of Economics and Finance* 48(1):142-165, March 2024. The study used 1,658 NBA projections from four providers, collected in February 2022 (DFS context). Findings:
  - "professional forecasts reduce errors made in naïve forecasts, but only to a moderate extent."
  - Forecasts were "inefficient and, in some cases, even biased."
  - Providers showed notable short-run differences but only "small, although in one case significant, long-run differences."
  - Simulated competitions "raise doubts as to whether the forecasts provided are worth the money." A free provider (Daily Fantasy Fuel) was not beaten significantly by paid ones.
  - The four providers are not all named in the accessible abstract.
  — [RePEc/IDEAS](https://ideas.repec.org/a/spr/jecfin/v48y2024i1d10.1007_s12197-023-09646-7.html); [OUCI record](https://ouci.dntb.gov.ua/en/works/7nDP3Bml/); [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- (NFL, labeled) FantasyPros 2010: consensus ranked #2 of 40+ experts, and a top-5 consensus beat all individuals (see Q2). — [FantasyPros 2011](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)
- (Soccer, labeled, general crowd wisdom) Collective crowd predictions outperformed individual estimates in football (soccer) match prediction. — [PMC11785260, "Goal-line oracles"](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11785260/)

### Inferences
- Döpke et al.'s finding that forecasts are "inefficient/biased" implies that a simple bias-correction or combination of providers could improve on any one of them. That is the same logic by which ECR beats individual rankers.
- If professional projections beat naive ones only moderately, BPV's ~0.3 FP/G deficit to ECR is plausibly within the size of the "news/role" edge rather than a sign of a fundamentally broken model. This is untested.

### Gaps
- No r/fantasybball or blog season-long projection accuracy comparison was located, whether by search or because Reddit was not indexed.
- The fantasycalc performance-analysis page did not render.
- There is no NBA evidence on whether combining a stats model with ECR beats ECR alone.

## Q5. What information human experts use that stats models lack, and evidence that it explains their edge

### Takeaway
Sources consistently say the human layer adds **minutes/role/lineup/injury news** (coaching tendencies, injury timelines, confirmed starters, depth-chart changes) and fast updates. However, I found no study that isolates news as the source of experts' edge in fantasy basketball. The NFL consensus data (consensus improves late season; ECR sits near the top) is consistent with, but does not prove, an information-aggregation explanation.

### Cited Findings
- RotoWire's analyst review covers "coaching tendencies, injury recovery timelines, and lineup changes that emerge throughout the day," with adjustments made the moment the injury report or lineups are confirmed. — [RotoWire](https://www.rotowire.com/basketball/projections.php)
- Basketball Monster updates short-term projections "as soon as news happens" and full-season projections several times daily. — [BBM Help](https://basketballmonster.com/Help.aspx)
- Minutes are the dominant input: "minutes matter far more than a single game's shooting percentage." — [RotoWire](https://www.rotowire.com/basketball/projections.php); [RotoGrinders](https://rotogrinders.com/fantasy/lessons/nba-player-projections)

### Inferences
- For BPV, the likely sources of ECR's edge, in rough order of plausibility:
  1. Games-played/availability expectations (injury history, load management, pending injuries) embedded in ranks.
  2. Minutes/role changes from offseason moves, camp news, depth charts and coaching quotes.
  3. Error-cancellation from averaging 40+ rankers.
  4. Implicit aging/development curves.
- A testable approach is to decompose BPV-vs-ECR error into a minutes component and a per-minute-rate component, and to check whether the gap concentrates in players with offseason team/role changes or injury flags. Blending BPV with ECR would test whether the two carry complementary information.

### Gaps
- No empirical study was found attributing expert edge in fantasy basketball to news. This remains an untested hypothesis.
