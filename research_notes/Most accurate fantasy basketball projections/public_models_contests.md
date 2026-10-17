# Public NBA projection models and prediction contests: accuracy evidence

Scope note: research done 2026-09-29, with about 20 search/fetch calls. APBRmetrics pages were read through an LLM summarizer (WebFetch), so the table values below are as the summarizer extracted them. Items marked **[snippet-only]** come from search-result snippets and were not confirmed on a fetched page. Throughout, evidence is tagged as **TEAM-LEVEL** (win totals or team net rating) or **PLAYER-STAT-LEVEL** (box-score or fantasy stats), because the two answer different questions.

## Q1. APBRmetrics preseason team-win contests: who won, by how much, and does winning persist?

### Takeaway
TEAM-LEVEL only. No single public model wins every year. Hobbyist entrants built on simple metrics with age adjustments (dtkavana/CraftedPM, "mediocre"), the entrant average (avgA), and Vegas usually finish close to or ahead of DARKO, LEBRON, EPM and Pelton. The gap between first place and the Vegas line is usually only 0.5–1.5 wins of MAE. DARKO ranks high in some seasons and mid-pack in others, so the persistence evidence is weak.

### Cited Findings
- **2020-21** (final standings May 17, 2021). MAE / RMSE: 1. EExp (ESPN expert aggregate) 5.47 / 7.13; 2. Vegas 5.55 / 7.37; 3. Shadow 5.73; 4. TeRa 5.74; 5. bbst 5.82; 6. Caliban 5.88 / 7.68; 7. Crow 5.93; 8. avgA 5.95. Lower in the table: dtka 6.13, DSM1 6.17. 538 Elo and EBPI trailed. — [APBR 2020-21 contest](https://apbr.org/metrics/viewtopic.php?p=37970). Caveat: the summarizer labeled "dtka" as DARKO, but on APBR dtka is dtkavana (CraftedNBA), so I do not treat that row as a DARKO result. The page also reportedly says "Shadow" won on MAE, which conflicts with the table. This is likely a win among contestants only, excluding benchmarks such as EExp and Vegas. Unverified.
- **2021-22** (Mike G's error table, March 31, 2022). Avg error / RMSE: 1. trzu (tarrazu) 6.59 / 8.21; 2. cali 6.77; 3. shad 6.91; 4. "5.38" (FiveThirtyEight) 6.91 / 8.48; 5. avgA 7.05; 6. vegas 7.07 / 8.92; 7. dtka 7.10; 8. emin 7.12; 9. Crow 7.14. — [APBR 2021-22 contest p.7](https://apbr.org/metrics/viewtopic.php?t=9903&start=90)
- 2021-22: DARKO was not an official entrant. On March 25, 2022 kmedved (Medvedovsky, DARKO's creator) said "The preseason-only model ... is dominating." Crow replied that "Darko without preseason is just on par with the 2 blends" (March 28, 2022). Crow also asked whether "EPM's reputation [would] take a hit" (March 24, 2022), and LEBRON and RAPTOR were also described as disappointing. — [APBR 2021-22 p.7](https://apbr.org/metrics/viewtopic.php?t=9903&start=90). **[snippet-only]**: "Darko finished 1st in an expanded check of 30 listings, while LeBron finished 19th." — [search snippet, APBR 2021-22](https://apbr.org/metrics/viewtopic.php?t=9903&start=90)
- **2022-23** (Mike G, March 27, 2023, near the end of the season). Avg error / RMSE / R²: 1. dtka 5.07 / 6.15 / .64; 2. avgA 5.45 / 6.44 / .60; 3. vzro 5.59; 4. KPel (Kevin Pelton) 5.60 / 6.68 / .54; 5. LEBR (LEBRON) 5.72 / 6.46 / .59; 6. DRKO (DARKO) 5.81 / 6.79 / .55; 7. Crow 5.90. — [APBR 2022-23 p.11](https://apbr.org/metrics/viewtopic.php?t=9946&start=150). In another thread, Mike G said DARKO finished 5th in MAE and 4th in RMSE of 19 in the 2023 contest. — [APBR "Comparing BPM and DarkoPM"](https://apbr.org/metrics/viewtopic.php?t=10046). **Conflict:** a snippet says "Darko would have been in first place, LEBRON/EPM 5th or 6th" in 2022-23. **[snippet-only]**, and probably taken from a different snapshot date.
- **2023-24** (snapshot Feb 26, 2024, **not final**). Avg error: medi 4.95 (RMSE 6.3, r² .78); ChKl 5.85; EExp 5.86; vegas 6.15; Crow 6.89; EBPI 7.27; KPel 7.63; DARKO 7.70; LEBR 8.15. — [APBR 2023-24 p.11](https://apbr.org/metrics/viewtopic.php?t=10034&start=150). **[snippet-only]**: "Darko finished 13th of 20 listings, LeBron 18th." — [search snippet](https://apbr.org/metrics/viewtopic.php?t=10034&start=150)
- **2024-25** (final, April 13, 2025). MAE / RMSE / R²: 1. dtkavana 7.50 / 9.7 / .46, using prior-season CraftedPM with an age adjustment ("Two wins in three years", Apr 14, 2025); 2. TeemoTeejay (MAMBA metric) 7.63; 3. avgA 7.82; mediocre 7.87; DQuinn1575 7.93; Vegas 8.40 / 10.7 / .38; KPel 8.52 / 10.0 / .58. DARKO was not entered. kmedved reported DARKO afterwards at 7.24 MAE, 9.15 RMSE, .533 R² (Apr 29, 2025), which would have been the best score. That number is self-reported after the fact and was not a pre-registered entry. — [APBR 2024-25 p.17](https://apbr.org/metrics/viewtopic.php?t=10146&start=240)
- 2024-25 methods: DARKO used Basketball Monster minutes projections, while LEBRON and several other entries used Kevin Pelton's minutes. — [search snippet, APBR 2024-25](https://apbr.org/metrics/viewtopic.php?t=10146&start=150) **[snippet-only]**
- **2025-26**: the thread exists (about 180 replies, last post by Crow on Apr 14, 2026). I could not retrieve its final standings. — [search snippet](https://apbr.org/metrics/viewforum.php?f=2) **[snippet-only]**. A thread for the next contest ("2027 NBA team wins prediction contest", t=10289) opened Sep 25, 2026. — [APBR forum index](https://apbr.org/metrics/viewforum.php?f=2)
- Persistence: as of 2023, Crow and tarrazu each had three contest wins, reportedly the only repeat winners. — [APBR 2022-23 p.11](https://apbr.org/metrics/viewtopic.php?t=9946&start=150). dtkavana won in 2022-23 and 2024-25. — [APBR 2024-25 p.17](https://apbr.org/metrics/viewtopic.php?t=10146&start=240)
- The simple average of entries (avgA) finishes in the top 2–5 in most years. Mike G linked this to the forecasting literature on averaging. — [APBR 2022-23 p.11](https://apbr.org/metrics/viewtopic.php?t=9946&start=150)
- Kevin Pelton has written that, in the APBRmetrics scoring, his recalibrated forecast had the second-lowest RMSE and the highest correlation with actual wins in one season. The season is not specified in the snippet. — [ESPN SCHOENE explainer](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system) **[snippet-only]**

### Inferences
- Across 2020-25, Vegas's MAE is usually within about 1 win of the winner, and it often beats the named public models. For team wins, the market is a hard benchmark to beat.
- Contest entries mix a player metric with separate minutes, injury and trade assumptions, and entrants use different minutes sources. The result therefore tests the full pipeline, not just the player metric. This makes the contest weak evidence about which model projects individual box-score stats best.
- The winner changes nearly every year and the spreads are small: 30 teams, one season, with MAE differences of 0.2–0.5 wins between neighboring ranks. That points to heavy noise, and one season's rank should not be read as a lasting skill ranking.

### Gaps
- Final 2023-24 and 2025-26 standings, and 2014-2020 results, were not retrieved.
- No independently maintained multi-year leaderboard was found. Nathan Walker, Dan Chen and Kaggle contests were not found in the time available.
- Before 2022-23 DARKO was not always an official entrant, so its "would have finished" placings are after-the-fact checks.

## Q2. Retrodiction and prediction comparisons of impact metrics: what they show and why they matter little for fantasy

### Takeaway
TEAM-LEVEL. The best-known comparison was run by EPM's own creator in 2020. It predicted next-season team net rating from player metrics and found EPM best (RMSE 2.48), followed by RPM, RAPTOR and BPM. None of these tests predict per-game points, rebounds or assists. They measure all-in-one impact, which is not what fantasy scoring rewards.

### Cited Findings
- Dunks & Threes "NBA Player Metric Comparison" (June 17, 2020, Taylor Snarr, **EPM's creator, so not independent**). Method: player metric values from season N predict adjusted team net rating in N+1, over 2013-14 to 2019-20 (six season pairs, 180 team-seasons). Players with 250+ minutes were included and rookies were set to replacement level. RMSE: EPM 2.48, RPM 2.60, RAPTOR 2.63, BPM 2.71, PREDATOR 2.73, PIPM 2.78, RAPM 2.80, WS48 2.85, aPER 3.12, PER 3.20. DARKO and LEBRON were not included. — [Dunks & Threes](https://dunksandthrees.com/blog/metric-comparison)
- A search snippet claims "DPM beats all the other public-facing metrics in predictive power based on RMSE, next best EPM and LEBRON" and that EPM led after controlling for roster continuity. The first claim's original source could not be identified; an exact-phrase search failed. **[snippet-only; unattributed]** — [search results incl. cryptbeam "10 best impact metrics" (site unreachable)](https://www.cryptbeam.com/2021/05/21/the-10-best-nba-impact-metrics/)
- A HoopsHype poll of NBA team staff ranked DPM first among public all-in-one metrics: 8 of 29 named it their preferred metric and 10 more said they trusted it. This measures opinion, not accuracy. — [darko.app/about](https://www.darko.app/about), citing [HoopsHype 2021](https://www.hoopshype.com/story/sports/nba/2021/09/17/advanced-stats-nba-real-plus-minus-rapm-win-shares-analytics/75615174007/)
- DARKO shrinks low-minute players and rookies (e.g., Wembanyama, Holmgren) strongly toward priors. That helps prediction but can lag real breakouts. — [APBR "Comparing BPM and DarkoPM", Nov 2023](https://apbr.org/metrics/viewtopic.php?t=10046)
- FiveThirtyEight RAPTOR and its projection system (the successor to CARMELO) stopped updating after Disney's 2023 changes. Neil Paine publishes an "estimated RAPTOR" on Substack. — [Neil Paine](https://neilpaine.substack.com/p/nba-estimated-raptor-player-ratings); [538 RAPTOR methodology](https://fivethirtyeight.com/features/how-our-raptor-metric-works/)

### Inferences
- These comparisons rank metrics on how well they predict team point differential. Fantasy value depends on counting stats and percentages, and a player's plus/minus impact can differ a lot from his fantasy line, for example a low-usage defender. Winning these tests says little about fantasy box-score accuracy.

### Gaps
- No independent third-party retrodiction test covering DARKO, EPM, LEBRON and BPM together was found. BBall Index's own LEBRON validation and Ben Taylor's comparisons were not retrieved.

## Q3. Direct comparisons of stat-level (per-game box score) projections

### Takeaway
PLAYER-STAT-LEVEL. The only direct stat-level comparison found is DARKO's own claim: its projections beat two paid DFS projection sites on every stat tested except minutes. The test was run by DARKO's creator, and the sites, years, sample and error metric are not published. I found no independent check.

### Cited Findings
- darko.app/about says DARKO "beat both sites in every stat tested (minutes, points, rebounds, assists, blocks, turnovers, and threes made), some by substantial margins," but that minutes "remain difficult to forecast." — [darko.app/about](https://www.darko.app/about). The older description (via search snippet) says Medvedovsky collected two years of daily projections from two sites selling DFS projections and converted DARKO's rate projections to game-level projections. It also refers to "three years of data" **[snippet-only]**. — [buymeacoffee.com/darko](https://buymeacoffee.com/darko)
- DARKO projects every player for every box-score stat each day, and its projections are updated daily. — [darko.app/about](https://www.darko.app/about)
- An APBRmetrics thread on predicting player stats directly contains no quantitative comparisons between systems. — [APBR "Has anyone tried to predict player stats directly?"](https://apbr.org/metrics/viewtopic.php?t=9848&p=37413)
- Pelton's SCHOENE produces per-game stats that feed ESPN's fantasy projections. No published accuracy test of those stats was found. — [ESPN SCHOENE explainer](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system) **[snippet-only]**

### Inferences
- DARKO's DFS claim concerns game-level daily projections, which is not the same as preseason season-long per-game averages. It also excludes minutes, and minutes drive most fantasy error.

### Gaps
- No independent test was found comparing DARKO, EPM, SCHOENE or others against fantasy sites (ESPN, Yahoo, Basketball Monster, Hashtag, FantasyPros) on season per-game stats.

## Q4. Availability: which models give fantasy-usable per-player box-score projections, what they cost, and whether they can be captured each preseason

### Takeaway
DARKO (darko.app) is the strongest candidate. It is free, has per-stat projections and a "Fantasy Lab" projections page, and offers CSV exports. EPM, LEBRON and RAPTOR are mainly impact ratings, not box-score projections. Pelton's per-game stats are published only inside ESPN's fantasy projections.

### Cited Findings
- As of June 2026, the old DARKO Shiny app (apanalytics.shinyapps.io/DARKO) is offline and redirects to www.darko.app. — [old DARKO app](https://apanalytics.shinyapps.io/DARKO/_w_e615d302/)
- darko.app offers leaderboards, team pages, a Compare tool, standings, WOWY, lineups, longevity and a "Fantasy Lab" (/projections), all with CSV exports. It rates about 530 players daily, has data back to 1996-97, and shows no pricing (it appears free). Projected stats include points, rebounds, assists, blocks, turnovers, 3PM, shooting percentages and role/playing time. — [darko.app/about](https://www.darko.app/about); [darko.app](https://www.darko.app/)
- In November 2023, DARKO data was also mirrored to a Google Sheet that updated daily, per kmedved. — [APBR thread](https://apbr.org/metrics/viewtopic.php?t=10046)
- CraftedNBA publishes preseason projections for 2025-26 and re-hosts DARKO values. — [craftednba.com/projections](https://craftednba.com/projections); [Charting Hoops, Feb 2026](https://chartinghoops.substack.com/p/advanced-darlings)
- Pelton's projections run through ESPN, partly behind the ESPN+ Insider paywall. Per-game SCHOENE stats appear in ESPN fantasy projections. — [ESPN win projections 2025-26](https://www.espn.com/nba/story/_/id/46521096/nba-2025-2026-season-win-projections-all-30-teams); [ESPN SCHOENE explainer](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system)
- The FiveThirtyEight RAPTOR and CARMELO projections are discontinued. Their historical data is on GitHub. — [fivethirtyeight/data nba-raptor](https://github.com/fivethirtyeight/data/blob/master/nba-raptor/README.md)

### Inferences
- To test "most accurate fantasy projections" going forward, DARKO's preseason box-score projections can be captured free each year: snapshot the CSV before opening night. Nothing found here offers the same for EPM or LEBRON box-score projections.

### Gaps
- I did not confirm whether the darko.app Fantasy Lab gives season-long per-game projections or only next-game projections, and I did not check for any paywall behind a login.
- EPM (Dunks & Threes, which has a paid tier) and LEBRON (BBall Index, paid) pricing, and whether either publishes box-score projections, were not verified.
- Basketball-Reference SPS, Inpredictable and The Athletic projections were not researched in the time available.
