# Public NBA and baseball player projection systems: methods, accuracy, and what can be rebuilt from box-score logs

Research date: 2026-09-29. Scope: DARKO, EPM, LEBRON, RAPTOR/CARMELO, SCHOENE, BBRef SPS, Marcel, Steamer, ZiPS, PECOTA, THE BAT, and head-to-head accuracy evidence. Context: BPV projects ESPN points-league FP/G from box-score game logs. Earlier BPV tests of "SPS averaging", "older seasons/decay windows" and "per-stat recency/age" did not beat the simpler version.

Source-access caveats: fivethirtyeight.com now 301-redirects to abcnews.com, and web.archive.org was blocked from this tool, so there are no primary CARMELO/RAPTOR documents. steamerprojections.com/blog/methods returned HTTP 500. Two Beyond the Box Score grading articles hit ECONNRESET, so their numbers come only from search snippets. The DARKO stabilization-table values are an image and could not be read.

## DARKO (Kostya Medvedovsky): exponential decay + Kalman filter per stat, game weighting, aging, box-score projections, accuracy

### Takeaway
DARKO projects every box-score component separately. Each stat has its own exponential decay rate, fit by an optimizer against future performance, and measured in days, not seasons. A modified Kalman filter runs alongside the decay, and a gradient-boosted tree combines the two with adjustments: stat-specific age curves, rest/travel/home, opponent, seasonality, interactions between stats, and team changes. The fitted half-lives differ enormously by stat. Playing time is about 3 games, scoring about 31 games, 3P% about 1.5 seasons. That spread is the key design fact for BPV.

### Cited Findings
- DARKO = "Daily Adjusted and Regressed Kalman Optimized". It is a machine-learning box-score projection system that updates daily. It was trained on every player game log since 2001 (about 736,000 at the time), using Basketball-Reference, NBA.com and pbpstats data — [search summary of DARKO docs](https://apanalytics.shinyapps.io/DARKO/_w_66db5831/). The shinyapps site moved offline in June 2026; the docs now live at [darko.app/about](https://www.darko.app/about).
- Game weighting: each game is weighted by β^t, where 0<β<1 and **t = days since the game**. β differs by stat, is "selected to best predict future results", and is fit with a **differential evolution optimizer**. β near 1 weights all history about equally; smaller β favors recent games — [darko.app/about](https://www.darko.app/about).
- Reported half-lives by stat: starting role ~1 game; playing time ~3 games; usage rate ~17 games; assist rate ~24 games; scoring ~31 games; 3P% ~1.5 seasons; corner-3 % ~8 seasons — [darko.app/about](https://www.darko.app/about).
- A "modified Kalman filter" runs alongside the decay model to separate noisy measurements from underlying talent. A **gradient-boosted decision tree merges the decay and Kalman projections** into the final stat forecast — [darko.app/about](https://www.darko.app/about).
- Adjustments, each applied per component: rest/travel/home court; opponent strength; **age curves, one per stat, built to address selection bias** (survivor bias in aging curves); seasonality (within-season trends); interaction effects ("simultaneous improvements treated more credibly", i.e. a player improving in several correlated stats at once is believed more); and a higher learning rate after a trade or free-agency move — [darko.app/about](https://www.darko.app/about).
- Rookies start from **age, draft position and height**, then update from games, with the most sensitivity early in the career — [darko.app/about](https://www.darko.app/about).
- Accuracy vs other box-score projections: DARKO "beat both sites in every stat tested (minutes, points, rebounds, assists, blocks, turnovers, and threes made)". The exception was minutes/playing time, described as "the hardest part of any projection system". A second fetch of the same page named the comparison sites only as "DFS projections" — [darko.app/about](https://www.darko.app/about). The seasons, error metric and site names were not retrievable.
- Per-stat "padding" regression (Medvedovsky, 2020-08-06). For each stat he searched, by differential evolution, for a constant number of league-average observations to add to year-to-date totals. The target was rest-of-season performance, fit on about 750K player-game rows since 2001. The padding is constant through the season, so the data dominates as the sample grows. Example: expected 3P% = (makes + X·lg%)/(attempts + X), with X ≈ 240 attempts. The page text says both 240 and 242. Minutes are "extremely stable… almost entirely a coach's decision". Plus/minus needs over 1,000 league-average possessions of padding. The full per-stat table is an image and could not be read — [kmedved.com: NBA Stabilization Rates and the Padding Approach](https://kmedved.com/2020/08/06/nba-stabilization-rates-and-the-padding-approach/).
- The same post cites Darryl Blackport's 2014 estimate that 3P% needs about 750 attempts to "stabilize" (KR-21 reliability), contrasting it with the ~240 padding. The two methods answer different questions: KR-21 finds the sample where reliability reaches 0.5, while padding optimizes forecast error — [kmedved.com](https://kmedved.com/2020/08/06/nba-stabilization-rates-and-the-padding-approach/).
- An RMSE comparison of all-in-one impact metrics' predictive power (Medvedovsky tweet, 2021-01-30, via NBAstuffer) ranked DPM (DARKO) 1st, EPM 2nd and LEBRON 3rd. EPM "especially stands out" on MAE and R² — [NBAstuffer DARKO page](https://www.nbastuffer.com/analytics101/darko-daily-plus-minus/). This is a secondary source, and the test design is not described there.

### Inferences
- DARKO's recency handling works because (a) each component gets its own decay, fit against a forward-looking target by an optimizer rather than hand-picked; (b) decay runs on **days**, so the offseason gap automatically discounts last season versus this season; and (c) rate stats and opportunity (minutes, starting role) are modeled separately, with opportunity decaying extremely fast. If BPV's "per-stat recency" test used hand-picked decay values, one shared window for minutes and rates, or decayed per-game FP totals rather than per-minute rates × minutes, it would not reproduce what makes DARKO work.
- The half-lives imply that minutes should be decayed hard (a few games) while per-minute scoring and assist rates should use roughly a 20–35 game half-life. Shooting percentages should use multi-season windows plus heavy padding. A single "older seasons" window applied to FP/G mixes these, and can lose to a simple recent-season average because FP/G is dominated by minutes × usage, which are the fast-decaying components.
- For a **preseason** (season-ahead) projection, most of DARKO's in-season machinery (Kalman, rest, opponent) adds little. What transfers is per-stat decay with a days-based offseason gap, per-stat padding toward league (or position/archetype) means, per-stat age curves, and a draft/age/height prior for rookies.
- Reproducible from box-score logs + age + draft: per-stat β fit (scipy `differential_evolution` against next-N-games or next-season per-minute rates), per-stat padding constants, per-stat age deltas via the delta method with survivor correction, and a rookie prior from draft pick + age. Height is not in BPV's stated inputs. The GBDT stacking layer is reproducible; the tracking/pbp inputs are not.

### Gaps
- The exact β/half-life for rebounds, blocks, steals, turnovers, FT% and FTA rate was not listed on the page. Neither was the full padding table (image only).
- The accuracy test's sites, seasons and metric are not documented in retrievable text. No independent audit of DARKO box-score projections was found.
- How the Kalman filter's process/measurement noise is set and how the GBDT is trained was not documented.

## EPM (Dunks & Threes, Taylor Snarr), LEBRON (BBall Index), RAPTOR/CARMELO (FiveThirtyEight): projections and comparables

### Takeaway
EPM's "Estimated Skills" use the same idea as DARKO: exponentially decayed, per-stat decay factors chosen by stabilization rate, plus age, seasonality and opponent adjustments. LEBRON is a descriptive impact metric (box prior + luck-adjusted RAPM) with no published projection method. CARMELO was a PECOTA-style comparables system, but its primary documentation is no longer reachable.

### Cited Findings
- EPM = an SPM model (box score, play-by-play and tracking inputs, trained on RAPM from 2001-02 to 2018-19; tracking model trained 2017-18 to 2022-23) combined with RAPM. It updates nightly, with values since 2001-02 — [dunksandthrees.com/about/epm](https://dunksandthrees.com/about/epm).
- EPM "Estimated Skills" use exponentially decayed weights with a decay factor between 0 and 1. **"Different stats have different optimal decay factors based on stabilization rates"**, and the full career informs the estimate, weighted toward recent games — [dunksandthrees.com/about/epm](https://dunksandthrees.com/about/epm).
- EPM adjusts for age (varies by stat), within-season trends, time on current team, opponent strength, back-to-backs and seasonality. Game predictions use "predicted minutes at each point in time" plus official inactives. Cross-validated 2002–2023 margin-of-victory RMSE is 12.1 points — [dunksandthrees.com/about/epm](https://dunksandthrees.com/about/epm).
- LEBRON uses boxPIPM-weighted box stats, **stabilized differently by offensive archetype**, as a prior for luck-adjusted RAPM (expected rather than observed teammate 3P/FT shooting) — [BBall Index LEBRON Introduction](https://www.bball-index.com/lebron-introduction/), [LEBRON Box Prior](https://www.bball-index.com/lebron-box-prior/) (both via search summary).
- BBall Index year-to-year repeatability, 2013-14 to 2025-26: DPM 0.85, BBI "Overall Talent" 0.81, BPM 0.78, LEBRON 0.77, EPM 0.75, LA-RAPM 0.50, RAPM 0.41. The article argues impact = talent + context, so raw past impact projects poorly when role or team changes. It gives no explicit projection formula — [BBall Index: Your Impact Stat Isn't Coming Back Next Year](https://www.bball-index.com/projecting-impact/) (undated).
- CARMELO (Career-Arc Regression Model Estimator with Local Optimization; Nate Silver, 2015) is based on PECOTA. It defines player skills and then finds similar historical players. Similarity starts at 100 and loses points for differences across **19 categories**, some weighted more heavily — [search summary of FiveThirtyEight 2015 methodology](https://fivethirtyeight.com/features/how-were-predicting-nba-player-career/) (original now redirects to abcnews.com). CARMELO projected WARP from a blend of RPM and BPM, and was later replaced by RAPTOR-based projections — [NBAstuffer CARMELO](https://www.nbastuffer.com/analytics101/carmelo/).

### Inferences
- Two independently built leading systems (DARKO, EPM) converge on the same design: per-stat decay tuned to each stat's stabilization, plus per-stat age. That is strong evidence the per-stat approach is right when done with optimized parameters and a forward target. A failed BPV test more likely points to implementation or target issues than to the idea itself.
- LEBRON's archetype-specific stabilization suggests regressing toward a role/archetype mean (e.g. by position or usage tier) rather than the league mean. Box-score logs can approximate this with clusters of per-minute stat profiles.
- CARMELO/RAPTOR comparables target all-in-one ratings, not box-score components, so they transfer to FP only via SCHOENE-style per-stat comps.

### Gaps
- Exact EPM decay factors, the age curve shape and the minutes model were not published in retrieved text. No accuracy figure for EPM *player box-score* projections was found.
- CARMELO's category list, weights, number of comps and aging details are unrecoverable here because the primary pages redirect. The RAPTOR-era projection method was also not retrieved.
- No LEBRON projection methodology was found.

## Kevin Pelton's SCHOENE: similarity comparables, per-stat projections, minutes

### Takeaway
SCHOENE builds an age-weighted three-season baseline, adjusts it for league, then finds the 50 most similar players at the same age (±6 months) across 13 categories including height and weight. Their subsequent development drives the aging projection. It adds a regression factor and a separate games-missed injury model.

### Cited Findings
- "Performance over the past three seasons, weighted by age, generates a baseline projection", adjusted for league. The system finds the most similar past players in **13 categories (including height and weight)** at the same age, **within six months either way**. 100 is a perfect match; >95 is very similar and >90 is some similarity — [ESPN, Pelton, "Explaining the SCHOENE projection system", 2013-10-09](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system).
- "For most players, SCHOENE uses a pool of 50 comparable players" to estimate how age will affect performance — [ESPN 2013](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system).
- A regression factor was added to baselines to filter "fluky performances". A new model projects **games missed due to injury from games missed over the past three seasons**, with larger penalties for repeated long absences — [ESPN 2013](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system).
- SCHOENE also projects from translated D-League/Euroleague/EuroCup/ACB stats — [ESPN 2013](https://www.espn.com/nba/story/_/id/9797404/explaining-schoene-projection-system).

### Inferences
- A per-stat comps-based aging model is reproducible from game logs + ages. Heights and weights would need an extra source. The expected gain over a smooth per-stat age curve is uncertain (see ZiPS/PECOTA vs Marcel below).
- SCHOENE's separate availability model (games missed from 3-year history) is relevant if BPV's target is season-total FP. It is irrelevant for FP/G.

### Gaps
- The 13 categories, the three season weights, how the 50 comps are weighted, and the minutes-per-game model are not stated. No published accuracy numbers for SCHOENE were found.

## Basketball-Reference Simple Projection System (SPS): weights, regression, age

### Takeaway
SPS is Marcel ported to basketball. Weights are 6/3/1 by season; regression adds 1,000 minutes of league-average production; the age adjustment peaks at 28 (+0.4%/yr younger, −0.2%/yr older). It makes no real minutes projection and uses one uniform regression for every stat.

### Cited Findings
- Weights 6 (most recent), 3, 1. Regression: compute the weighted league-average production for a player playing the same minutes, **scale it to 1,000 minutes**, and add it. Age: if under 28, multiply by (28 − age) × 0.004; if over 28, by (28 − age) × 0.002. The sign reverses for negative stats (missed shots, TOV, fouls) — [Basketball-Reference, About SPS](https://www.basketball-reference.com/about/projections.html). The page is undated; its worked example uses Dwight Howard's 2008-09.
- The page says SPS does not really project minutes, and that the projections are "basic", published because they were "easy" and "fun", yet "hold up quite well" against more sophisticated systems — [BBRef](https://www.basketball-reference.com/about/projections.html). No numbers are given.

### Inferences
- 6/3/1 is a per-season decay of roughly 0.5 then 0.33, heavy recency similar to Marcel's 5/4/3 in spirit but steeper. A single 1,000-minute padding for every stat over-regresses stable stats (minutes, rebounding and assist rate, likely the fastest-stabilizing per DARKO/EPM logic) and under-regresses noisy ones (3P%, steals, blocks). If BPV's "SPS averaging" test used BBRef's parameters unchanged, it tested a deliberately untuned baseline. Losing to a tuned BPV is expected and says little about whether per-stat regression works.
- A fair test would refit (a) the season weights and (b) a separate padding constant per stat on BPV's own target (next-season FP/G or per-minute stat rates), with minutes projected separately.

### Gaps
- No published SPS accuracy numbers. The "holds up well" claim is unquantified.

## Baseball systems (Marcel, Steamer, ZiPS, PECOTA, THE BAT): transferable ideas and accuracy

### Takeaway
Marcel (5/4/3, +1,200 PA of league average, age 29 peak, PT = 0.5·PA1 + 0.1·PA2 + 200) is the benchmark that complex systems beat only incrementally. Steamer, often the most accurate, is essentially Marcel with weights and regression backtested **separately per component**. ZiPS and PECOTA add comparables, with inconsistent payoff. Averaging systems usually beats any single system. Playing time is projected separately from rates, and ZiPS openly refuses to project it.

### Cited Findings
- Marcel: seasons weighted 5/4/3. Regression adds league average worth 1,200 PA, with league average itself weighted 5/4/3. Age: if over 29, (age − 29) × 0.003; if under 29, (age − 29) × 0.006, sign-corrected to 29 − age per post #20. **Projected PA = 0.5 × PA(last year) + 0.1 × PA(two years ago) + 200.** Rates are prorated to projected PA and re-baselined to league — [Tango, Marcel original thread](http://www.tangotiger.net/archives/stud0346.shtml).
- Marcel was designed as the "minimum level of competence that you should expect from any forecaster" — [search summary citing Baseball-Reference Marcel page](https://www.baseball-reference.com/about/marcels.shtml). Its logic is "three years of MLB data, with the most recent data weighted heavier. It regresses towards the mean. And it has an age factor", and other systems' algorithms give "only… incremental improvements in accuracy over the simian Marcel" — [THT, Sal Baxamusa, 2008-02-12](https://tht.fangraphs.com/the-running-of-the-monkeys/).
- Steamer "backtested a large number of different possible forecast systems, in order to determine the proper ratio of weights for data from recent seasons and **the correct amount of regression for each component of performance**". It adjusts for park, league, aging and SP/RP, and uses pitch-tracking data — [search summary of MLB glossary / Steamer About](https://www.mlb.com/glossary/projection-systems/steamer). The primary methods page returned HTTP 500.
- ZiPS: weighted multi-year data (four years; three for very young/old players). Aging comes from comparables, and weights are now research-tuned rather than uniform — [FanGraphs "Projection Rundown", 2011-02-16](https://library.fangraphs.com/the-projection-rundown-the-basics-on-marcels-zips-cairo-oliver-and-the-rest/). In 2026 it finds comps by **Mahalanobis distance** across about 185K hitter and 152K pitcher baselines, with the comp group used as "an ensemble model on the fly". **ZiPS does not project playing time** ("by design, ZiPS has no idea who will actually play") — [FanGraphs, Szymborski, 2025-11-12](https://blogs.fangraphs.com/the-2026-zips-projections-are-almost-here/).
- PECOTA (Silver/Baseball Prospectus) uses historical similar players — [FanGraphs 2011](https://library.fangraphs.com/the-projection-rundown-the-basics-on-marcels-zips-cairo-oliver-and-the-rest/). CAIRO is Marcel plus variable aging curves **by statistic**. Oliver uses weighted three-year averages with aging and regression — same source.
- FanGraphs "Depth Charts" = the ZiPS/Steamer average with FanGraphs custom playing time. This is the ensemble-plus-separate-PT pattern — [FanGraphs Projection Systems library](https://library.fangraphs.com/principles/projections/).
- Accuracy, 2015 (Beyond the Box Score): Steamer was most accurate in all five categories. ZiPS and PECOTA fell short of Marcel, with Marcel more accurate than both in each category — [BtBS 2016-01-14](https://www.beyondtheboxscore.com/2016/1/14/10733872/steamer-zips-pecota-marcel-projections-review) (search snippet; fetch failed).
- Accuracy, 2016 (BtBS): Steamer led again. ZiPS was least accurate of the three in all five categories. Marcel "beat ZiPS in four of five categories, and remains very hard to convincingly beat". **The average of all four systems beat every individual system in four of five categories**, trailing only Steamer in the fifth — [BtBS 2017-01-08](https://www.beyondtheboxscore.com/2017/1/8/14189138/pecota-zips-steamer-marcel-projection-systems-graded) (search snippet; fetch failed).
- THE BAT (Derek Carty) is listed in the FanGraphs library with no method detail — [FanGraphs](https://library.fangraphs.com/principles/projections/).

### Inferences
- Transferable ideas, ranked by evidence: (1) **per-component regression and weights fit by backtest** (Steamer's edge over Marcel; DARKO/EPM do the same); (2) **playing time projected separately from rates** (Marcel's PT formula; ZiPS omits PT; Depth Charts overlays PT); (3) **ensembles** (the average beats individuals in most categories); (4) comparables-based aging (ZiPS/PECOTA). Comps have the weakest evidence: in the retrieved comparisons ZiPS/PECOTA lost to Marcel.
- For BPV: project per-minute component rates (PTS, REB, AST, STL, BLK, 3PM, TOV, FGA/FGM, FTA/FTM) with per-component tuned padding and weights. Project MPG separately (Marcel-like: heavy on last season, regressed, plus role signals), then combine FP/G = Σ w_k · rate_k · MPG. This is a different model than regressing FP/G directly. It can beat a simple FP/G model mainly when players' component mix differs from the average, because the regression amounts differ by stat.
- Marcel's lesson cuts both ways. Expect the gains from sophistication to be small, which means BPV's earlier null results may be real rather than badly executed. Detecting small gains needs paired comparisons on the same players across several seasons (paired error differences with standard errors), not a single-season RMSE.

### Gaps
- Exact RMSE/MAE numbers and the categories in the BtBS studies (fetch failures). THE BAT and PECOTA internals (weights, comp counts) and Steamer's actual per-component weights are not public.

## Head-to-head accuracy studies of NBA projection systems

### Takeaway
Public head-to-head evidence is thin and mostly self-reported: DARKO's own box-score test, Medvedovsky's 2021 RMSE ranking of impact metrics (DPM > EPM > LEBRON), BBall Index year-to-year stability (DPM 0.85 highest), and APBRmetrics win-total contests, where rankings swing from year to year.

### Cited Findings
- DARKO self-test: it beat two unnamed projection sites (DFS projections) on points, rebounds, assists, blocks, turnovers and threes. Minutes was the exception — [darko.app/about](https://www.darko.app/about).
- Medvedovsky, 2021-01-30 tweet: impact metrics sorted by RMSE, DPM 1st, EPM 2nd, LEBRON 3rd; EPM best on MAE and R² — [NBAstuffer](https://www.nbastuffer.com/analytics101/darko-daily-plus-minus/).
- APBRmetrics team-win contests: DARKO placed first in one contest, where LEBRON and EPM "predictive versions" were 5th–6th. In other seasons DARKO finished 13th of 20 in one year and 1st in another, and LEBRON finished 19th and 18th — [search summary of APBRmetrics 2021-22 contest](https://apbr.org/metrics/viewtopic.php?t=9903&start=90) and [2024-25 contest](https://apbr.org/metrics/viewtopic.php?t=10146&start=150). These pages were not fetched directly, so the per-season attribution is unverified.
- HoopsHype survey: 8 of 29 NBA team staff ranked DARKO first among public all-in-one metrics — [darko.app/about](https://www.darko.app/about).
- APBRmetrics thread (Dec 2020) on predicting player stats directly: DSMok1 recommended DARKO. Another user reported game-prediction accuracy of 71% with perfect player projections versus about 67% with actual projections — [APBRmetrics t=9848](https://apbr.org/metrics/viewtopic.php?t=9848&p=37413).

### Inferences
- Win-total contests confound player projections with minutes allocation and team aggregation. The year-to-year rank swings show single-season comparisons are noisy, which also applies to BPV's internal tests.
- No public study was found that compares systems on **fantasy points per game** or per-stat box-score error across multiple seasons. DARKO's self-reported comparison is the closest.

### Gaps
- No independent, multi-season, per-stat accuracy study of NBA box-score projections (DARKO vs ESPN/Hashtag/FantasyPros/Basketball Monster etc.) was found.
- Nathan Walker's and other APBR posts on projection accuracy could not be located in this pass. Individual contest pages were not fetched to verify exact finishes.
