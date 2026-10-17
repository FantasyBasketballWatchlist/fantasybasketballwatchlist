# NBA DFS Projection Providers and Academic Studies of Fantasy Projection Accuracy

Research date: 2026-09-29. About 17 tool calls. Paywalled full texts (Springer) could not be fetched. Claims marked [snippet] come only from search-result snippets or abstract aggregators, not the full paper.

## Which DFS providers have published or independently measured projection accuracy (MAE/RMSE/correlation), and what were the results?

### Takeaway
I found only one independent, citable NBA DFS accuracy comparison: Döpke, Köhler & Tegtmeier (2024). It covers four providers, one month (Feb 2022) and 1,658 projections. All four had MAE of about 8 DK/FD fantasy points against an outcome SD of about 14. Daily Fantasy Nerd and Daily Fantasy Fuel scored best. None of the premium sim shops (Stokastic/Awesemo, SaberSim, ETR, FantasyLabs, LineStar, NumberFire, Rotowire, SportsLine) has a published or independent NBA accuracy audit that I could find.

### Cited Findings
- Döpke, Köhler & Tegtmeier (University of Applied Sciences Merseburg), "Are they worth it? – An evaluation of predictions for NBA 'Fantasy Sports'", *Journal of Economics and Finance* 48(1): 142–165, March 2024. Published online 23 Oct 2023. DOI 10.1007/s12197-023-09646-7. — [IDEAS/RePEc](https://ideas.repec.org/a/spr/jecfin/v48y2024i1d10.1007_s12197-023-09646-7.html); [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- Sample: 1,658 NBA projections from four providers, collected in February 2022. — [IDEAS/RePEc](https://ideas.repec.org/a/spr/jecfin/v48y2024i1d10.1007_s12197-023-09646-7.html)
- The providers named in the paper's table caption/snippets were Daily Fantasy Nerd (DFN, $29.99/mo), RotoGrinders ($64.99/mo, the most expensive), Daily Fantasy Fuel (free) and FantasyPros ($11.99/mo). [snippet] — [ResearchGate table page](https://www.researchgate.net/figure/Absolute-and-relative-accuracy-measures-by-provider-Daily-Fantasy-Nerd-RotoGrinders-Daily_tbl1_374925717); [search snippet of Springer text](https://link.springer.com/article/10.1007/s12197-023-09646-7). The free/paid status of DFF comes from my own knowledge that DFF is free, not from the paper.
- "For all providers the MAE is slightly lower or higher than 8 FPs, which shows a nontrivial magnitude of projection errors as compared to the standard deviation of the actual outcomes of slightly more than 14 FPs." By MAE, Daily Fantasy Nerd was best. [snippet] — [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- RMSE "shows an even larger magnitude of the average errors and a similar ranking of the providers' accuracy"; "the providers do not seem to be very different in terms of accuracy." [snippet] — [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- "The projections of the providers Daily Fantasy Nerd and Daily Fantasy Fuel are significantly better than those offered by other providers." A Diebold-Mariano test found the difference statistically significant in at least one pairwise comparison. The abstract says: "small, although in one case significant, long-run differences between the providers." [snippet + abstract] — [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7); [IDEAS](https://ideas.repec.org/a/spr/jecfin/v48y2024i1d10.1007_s12197-023-09646-7.html)
- Exact per-provider MAE/RMSE values were not retrievable (403 on ResearchGate, Springer paywall).
- SaberSim's NBA projections page makes no measured accuracy claims: no MAE/RMSE/correlation and no head-to-head comparison. It points to its sims and a "Winner's Circle" of user results. It has a $7/7-day trial and no free tier. — [SaberSim NBA projections](https://www.sabersim.com/nba/projections)
- Stokastic markets its projections as the "most accurate", built by "top pros with millions in verified winnings", but I found no published MAE or backtest. [snippet] — [Stokastic NBA](https://www.stokastic.com/nba); [Stokastic data](https://stokastic.com/data/nba-data)
- A Stokastic-published "best DFS tools" roundup (a competitor-authored ranking, so not independent) lists 4For4 for "projection accuracy" but gives no NBA metric. [snippet] — [Stokastic best DFS tools](https://www.stokastic.com/articles/dfs-strategy/best-dfs-tools)
- A different academic model (Springer *International Journal of Data Science and Analytics*, 2024, "An innovative method for accurate NBA player performance forecasting and line-up optimization in daily fantasy sports") reports validation MAEs of 7.33 and 7.74 fantasy points and MAPEs of 28.9% and 29.5%. [snippet; full text paywalled; unclear whether it benchmarked against commercial providers] — [Springer IJDSA](https://link.springer.com/article/10.1007/s41060-024-00523-y); [ResearchGate](https://www.researchgate.net/publication/379076776_An_innovative_method_for_accurate_NBA_player_performance_forecasting_and_line-up_optimization_in_daily_fantasy_sports)

### Inferences
- In the one controlled NBA comparison, a free source (DFF) was about as good as, or better than, the most expensive one (RotoGrinders). This is weak evidence against paying for projections, as opposed to paying for tools (sims, optimizers, ownership).
- MAE of about 8 DK points with an outcome SD of about 14 matches what hobbyist/academic models get (MAE about 7.3–7.7 in the IJDSA paper, on a different sample). That suggests a common error floor. Most leftover error is irreducible game-level variance (minutes, foul trouble, blowouts, late scratches), not model skill.
- Provider marketing claims of being "most accurate" (Stokastic, SaberSim) are unverified.

### Gaps
- Exact per-provider MAE/RMSE/Theil's U values and bias coefficients from Döpke et al.: paywalled.
- No independent NBA accuracy data found for Stokastic/Awesemo, SaberSim, ETR, LineStar, FantasyLabs, NumberFire, Rotowire, SportsLine. No r/dfsports or r/fantasybball backtest was surfaced by search (Reddit results were not returned). This means none was found, not that none exists.
- The Stanford STATS50 project "Beating DraftKings at Daily Fantasy Sports" (2016) reports MAE/RMSE, but the PDF could not be parsed. It is also outside the preferred date range. — [PDF](https://web.stanford.edu/class/stats50/projects16/BarryCanovaCapiz-paper.pdf)

## What did the academic studies find (providers compared, sample, bias, efficiency, whether paid beats free)?

### Takeaway
Döpke et al. found that the NBA DFS projections were inefficient, in some cases biased, and improved on a naive past-performance forecast by less than 10%. Paid providers did not beat the free one. The authors conclude that the results "raise doubts as to whether the forecasts provided are worth the money."

### Cited Findings
- Method: standard accuracy measures (MAE, RMSE, relative MSE vs a naive forecast); regression-based (Mincer-Zarnowitz-style) efficiency tests; Diebold-Mariano tests of equal accuracy; an optimization algorithm to build virtual DFS lineups from each provider; and a simulation of one-on-one contests between providers. — [OUCI abstract page](https://ouci.dntb.gov.ua/en/works/7nDP3Bml/); [Springer snippet](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- "Professional forecasts reduce forecast errors made by naïve forecasts by less than 10%." [snippet] — [ResearchGate](https://www.researchgate.net/publication/374925717_Are_they_worth_it_-An_evaluation_of_predictions_for_NBA_'Fantasy_Sports')
- Each provider has "better accuracy than that of a naïve projection based on these athletes' past performances." — [OUCI](https://ouci.dntb.gov.ua/en/works/7nDP3Bml/)
- "Applying regression-based tests of forecast efficiency, we find that the predictions are inefficient and, in some cases, even biased." — [IDEAS](https://ideas.repec.org/a/spr/jecfin/v48y2024i1d10.1007_s12197-023-09646-7.html)
- The simulated head-to-head DFS contests showed "small, although in one case significant, long-run differences between the providers." — [IDEAS](https://ideas.repec.org/a/spr/jecfin/v48y2024i1d10.1007_s12197-023-09646-7.html)
- Paid vs free: the price range was $0 (DFF) to $64.99/mo (RotoGrinders), and DFF and DFN (mid-price) were the significantly better pair. [snippet] — [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- Related academic literature cited by the paper: Beal et al. (2020) on AI optimization of DFS teams; Becker & Sun (2016); Haugh & Singal (2021, *Management Science*, "How to Play Fantasy Sports Strategically (and Win)"); South et al. (2019) on daily fantasy basketball. — [OUCI](https://ouci.dntb.gov.ua/en/works/7nDP3Bml/); [Haugh & Singal](https://pubsonline.informs.org/doi/10.1287/mnsc.2019.3528)

### Inferences
- "Inefficient" means the projections' errors were predictable from information available at the time (e.g. a slope below 1, so projections should be shrunk or stretched). A simple linear recalibration of any single source on your own backtest could reduce error. This is a cheap, actionable step for a season-long tool too.
- Main limitations: one month, four providers, and none of the high-end sim shops. It does not show that premium providers (ETR, Stokastic, SaberSim) are no better. It shows that price did not predict accuracy among the four tested.

### Gaps
- Which provider(s) were biased, and in which direction: not available without the full text.
- I found no other peer-reviewed NBA DFS provider comparison (2018–2026). I also found no academic study of "wisdom of crowds" specific to fantasy basketball.

## Is there evidence on combining/averaging projections in DFS (e.g. averaging sources beats individual ones)?

### Takeaway
There is no NBA-specific evidence. The best cross-sport evidence is NFL work by Fantasy Football Analytics. Their simple average beat individual sources in 63% of head-to-head comparisons over 11 seasons, and accuracy-weighted averaging did not beat equal weighting because source skill does not persist.

### Cited Findings
- FFA's "We Analyzed 11 Seasons of DFS Projections" (NFL, published Sept 2026): 9 sources (CBS, ESPN, NumberFire, FantasyPros, FFToday, FantasySharks, etc.) plus the FFA simple and weighted averages; more than 6,000 source-week combinations across 2015–2025. The FFA Average "outperformed individual sources in 63% of head-to-head comparisons" and had the most top-3 finishes. — [FFA 2026](https://fantasyfootballanalytics.net/2026/09/we-analyzed-11-seasons-of-dfs-projections-heres-what-we-found.html)
- Same study: "source accuracy simply does not persist reliably enough from season to season for historical weighting," so an equal-weight average does as well as a weighted one. — [FFA 2026](https://fantasyfootballanalytics.net/2026/09/we-analyzed-11-seasons-of-dfs-projections-heres-what-we-found.html)
- Same study: even the best projections explain only 3–23% of weekly variance (R²), depending on position. — [FFA 2026](https://fantasyfootballanalytics.net/2026/09/we-analyzed-11-seasons-of-dfs-projections-heres-what-we-found.html)
- Earlier FFA DFS and season-long accuracy pages use MAE as the primary metric and compare average vs weighted average vs single sources. — [FFA DFS accuracy](https://fantasyfootballanalytics.net/which-dfs-projections-are-most-accurate); [FFA season-long accuracy](https://fantasyfootballanalytics.net/which-projections-are-most-accurate)

### Inferences
- Given that Döpke et al. found NBA providers close together (MAE of about 8 for all) and inefficient, averaging NBA sources should reduce error, as in NFL. Averaging cancels source-specific noise, and near-equal accuracy is the setting where equal weights work best. This is inferred and has not been measured for the NBA.
- Caveat: NBA DFS sources share the same minutes/injury news inputs, so their errors are more correlated than NFL weekly projections. That would shrink the gain from averaging.

### Gaps
- I found no published NBA test of consensus vs single source (DFS or season-long).

## Are these projections free or paid, and can they be captured (CSV exports)? What does the DFS evidence imply for season-long projection accuracy?

### Takeaway
Free sources exist (DailyFantasyFuel; FantasyPros daily pages; RotoGrinders, Rotowire and Stokastic have partial free tables). The premium sim providers are paid. I did not verify CSV exports in this pass. For season-long use, the DFS literature says minutes, and fast news response on minutes, drive most of the accuracy. Rate stats are the easy part.

### Cited Findings
- Paid prices at Feb 2022 (per the paper): RotoGrinders $64.99/mo, Daily Fantasy Nerd $29.99/mo, FantasyPros $11.99/mo. [snippet] — [Springer](https://link.springer.com/article/10.1007/s12197-023-09646-7)
- SaberSim: $7 for 7 days trial, no free tier; CSV export not mentioned on the projections page. — [SaberSim](https://www.sabersim.com/nba/projections); [pricing](https://www.sabersim.com/pricing)
- SaberSim's projections come from play-by-play simulations and update "as news breaks". — [SaberSim help: How projections work](https://support.sabersim.com/en/articles/12078831-how-projections-work-in-sabersim)
- Public NBA daily projection pages exist at FantasyPros, Rotowire, Stokastic, SportsLine, FantasyAlarm, StatRankings and RotoGrinders. Paywall depth and export options are unverified. — [FantasyPros daily](https://www.fantasypros.com/nba/projections/daily-overall.php); [Stokastic projections](https://www.stokastic.com/nba/nba-dfs-projections); [SportsLine](https://www.sportsline.com/nba/expert-projections/simulation/); [RotoGrinders](https://rotogrinders.com/projected-stats/nba-player?site=rosters); [Rotowire](https://www.rotowire.com/basketball/projections.php)
- A practitioner guide notes that in NBA DFS "minutes played are the most volatile variable", and that accurate projections are usually built as fantasy points per minute × projected minutes. [snippet; vendor blog] — [Quadratic](https://www.quadratichq.com/use-cases/nba-dfs-projections-crafting-accurate-player-values); see also [RotoGrinders lesson on NBA projections](https://rotogrinders.com/fantasy/lessons/nba-player-projections)
- Döpke et al.'s naive benchmark (past performance) was beaten by less than 10%. The value providers add over a trailing average is small and likely concentrated in minutes/news adjustments. [snippet] — [ResearchGate](https://www.researchgate.net/publication/374925717_Are_they_worth_it_-An_evaluation_of_predictions_for_NBA_'Fantasy_Sports')

### Inferences
- For season-long rankings, per-game errors average out across about 70 games. The dominant error source becomes games played and minutes role: injuries, rotation changes, trades. DFS evidence that providers beat a trailing average by less than 10% suggests per-minute production is easy to project, and that the edge lies in minutes, availability and news speed.
- A season-long tool is likely to gain more from explicit minutes and games-played modeling plus a consensus of free sources than from subscribing to a single premium DFS provider.
- DFS projections are single-game and news-reactive, so they are poor direct inputs for season-long valuation. Their minutes projections, if captured daily, could serve as a live role signal.

### Gaps
- CSV export availability per provider was not verified. From memory, not sourced here: SaberSim, Stokastic, ETR and FantasyLabs typically allow CSV download for subscribers, and DFF offers free CSV downloads. This needs confirming.
- I found no study that directly measures how much of NBA DFS projection error comes from minutes vs per-minute rates.
