# Closing Line Value (CLV) as a Skill Measure, and Staking for Correlated NBA Player Props

Context for the reader: the team's model was tested on 592 NBA games (2024-25), with one Odds API snapshot per game taken about 1 hour before tip-off. On about 770 bets it came out near break-even at the best US price, with a 95% CI of about -6% to +8%. As a check, the per-bet SD of profit at -110 (decimal 1.91) is about 0.95 units, and 0.95/sqrt(770) gives a standard error of about 3.4%, so +/-6.7% is the expected width. The reported interval is consistent with pure noise.

Source quality warning: most CLV material is practitioner or vendor writing, not peer-reviewed. The most-cited numbers (CLV SD of about 0.1 vs P&L SD of about 1.0, and "about 50 bets") come from Joseph Buchdahl and are based on soccer and Pinnacle data. **No published study of CLV or closing-line efficiency for NBA player props was found.**

## 1. What CLV is, why it predicts profit, and how many bets each approach needs

### Takeaway
CLV is the ratio of the price you bet to the de-vigged closing price. If the close is roughly efficient, that ratio is an unbiased estimate of your expected value per bet, with about one tenth of the per-bet noise of realized profit. That cuts the number of bets needed to detect an edge by roughly 100x: at a 2% edge, a CLV test needs on the order of tens to a few hundred bets, while a profit test needs thousands to tens of thousands. The whole argument depends on the close being sharp, and for NBA props that is an assumption, not an established fact.

### Cited Findings
- **Definition.** Buchdahl defines CLV as "just the sportsbook's odds you have bet divided by the closing odds", where the closing odds are de-vigged to fair odds. Example: betting 2.10 when the fair close is 2.00 gives 2.10/2.00 = 1.05, about +5% expected value. — [Pinnacle Odds Dropper, Buchdahl on CLV](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- **Noise.** Buchdahl: "Whilst the typical standard deviation in even-money profits and losses will be about 1.00, the equivalent for CLV will be about 0.1." He says a bettor with a consistent ~5% CLV edge "might only need 50 bets to demonstrate significance", while a profit-based test needs "several thousand". — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- **CLV moving with actual yield.**
  - In Buchdahl's "Wisdom of the Crowd" system (about 20,000 bets), the realized yield was 3.4% against an expected value (the edge over fair odds) of 4.0%. — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
  - The football-data write-up (3 seasons, 22,318 matches) found that yield rose with the size of the advantage over fair odds: 3.40% yield at >0% advantage (22,281 bets), 6.63% at >2%, 12.70% at >4%. The author warns that the realized yields beat the predicted ones partly through "good fortune".
  - Caution: the "fair" price in that write-up comes from the author's own Pinnacle-based model, so it is not strictly a CLV measurement. — [football-data.co.uk, Wisdom of the Crowd](https://www.football-data.co.uk/blog/wisdom_of_the_crowd.php)
- **Correlation coefficient.** No source found reports a correlation coefficient between CLV and ROI across bettors. Buchdahl's evidence is that expected value matches realized yield in aggregate, not a cross-bettor correlation. — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- **Line movement as evidence of edge.** In the *Monte Carlo or Bust* sample of 952 +EV bets, 756 saw the price shorten or not move, with an average shortening of 3.94%. Buchdahl calls this "effectively impossible" by chance and says 65 bets would have been enough to show it. — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- **Sample-size formulas (practitioner source).**
  - Profit test: per-bet SD is about sqrt(o-1) under the null, and N = (z*s/e)^2.
  - At odds 2.00 with a 95% one-sided test: a 2% edge needs about 6,800 bets and a 1% edge about 27,100.
  - CLV test with SD 0.10: a 2% CLV needs about 70 bets and 1% about 270, at 95% one-sided. — [HowProsBet](https://howprosbet.com/how-to-verify-your-betting-edge/)
  - These figures ignore statistical power. A design with 80% power needs about 2.3x more bets (see the Inferences below).
- **Academic support for using the market as the benchmark.** Kaunitz, Zhong and Kreiner bet on bookmaker odds that stood out from the multi-book consensus.
  - Their abstract reports profitability over 10 years of historical closing odds, 6 months of minute-by-minute odds, and 5 months of real-money betting, followed by "discriminatory practices against successful clients" (account limits). — [arXiv 1710.02824](https://arxiv.org/abs/1710.02824)
  - Press coverage puts the backtest return at about 3.5% and the 5-month real-money return at 8.5%, using odds from 32 bookmakers over 2005-2015. These are secondary figures. — [Cosmos](https://cosmosmagazine.com/mathematics/researchers-work-out-how-to-break-the-bookmakers); [MIT Technology Review](https://www.technologyreview.com/2017/10/19/67760/the-secret-betting-strategy-that-beats-online-bookmakers/)
- **When CLV can mislead.**
  - Buchdahl says CLV is only a proxy for expected value and requires the close to reasonably reflect the true price.
  - He calls the close a "reasonable measure" for popular markets such as the Premier League and NFL. That implies less confidence for thin markets.
  - He also notes that originators (bettors with information the market lacks) may not show CLV. — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- **Prop markets may be less efficient.** Establish The Run says no single book is sharp on props the way books are on sides and totals; limits are low, and it names Caesars and FanDuel as the most efficient US prop books. That claim is about NFL props. — [Establish The Run](https://establishtherun.com/understanding-the-current-ecosystem-of-nfl-player-props/)
  - Vendor and blog sources also claim props are thinner and slower to correct, but they offer no data. — [topendsports](https://www.topendsports.com/betting-guides/sport-specific/nba/strategy.htm)

### Inferences
- The team's own numbers show the problem. With a per-bet SD of about 0.95 at -110, my simulation gives the following bets needed for a two-sided 95% test with 80% power: about **71,000 at a 1% edge, 17,800 at 2%, 7,900 at 3%**. For a test at 95% without the power requirement: about 35,000, 8,700, and 3,900. At about 770 bets a season, profit alone cannot settle a 1-3% edge in under several seasons.
- **CLV only helps if its own SD is small for props.** Buchdahl's SD of about 0.1 is for soccer and Pinnacle prices. Prop closing prices can move a whole line number, especially on injury or rotation news, so prop CLV SD is probably larger. If prop CLV SD were 0.2, a 2% mean CLV would need about (2.8*0.2/0.02)^2 = about 780 bets at 80% power, and 0.1 would need about 200. **Recommendation: measure the empirical SD of CLV on the existing data, by comparing the 1-hour-before price with a closing snapshot, before trusting any published N.**
- **CLV and outcome efficiency are separate claims.** Positive CLV against a US-book prop close proves the bettor anticipates where those books move. It only implies profit if that close is itself well calibrated. A **calibration check of the closing prop line** would test this: bin de-vigged closing probabilities and compare them with hit rates across all props, not just the bets placed. It uses data the team already has (close plus outcomes) and is cheap to run.

### Gaps
- No peer-reviewed study of NBA player-prop closing-line efficiency or CLV was found.
- No published cross-bettor correlation coefficient between CLV and long-run ROI was found. The evidence is aggregate expected value versus yield, in soccer.
- No source gave the empirical SD of CLV for player props.

## 2. Computing CLV for player props: de-vigging, line moves, and which close to use

### Takeaway
De-vig the closing two-way (over/under) price at the same line. For two outcomes, the additive method and Shin's method give identical results. Multiplicative is the crude baseline, and power or odds-ratio methods add a favorite-longshot correction. When the line number itself moves (for example 24.5 to 25.5), CLV needs a distribution model: fit a count distribution to the closing line and price, then evaluate it at your bet's line. For a sharp close, Pinnacle is the conventional benchmark, but its availability for NBA props and through the API has been restricted. A consensus no-vig line across several books is the practical fallback.

### Cited Findings
- **Formulas**, with r_i = 1/odds:
  - Basic or multiplicative: p_i = r_i / sum(r).
  - Additive: p_i = r_i - (sum(r) - 1)/n.
  - Power (also called logarithmic): p_i = r_i^(1/k), with k solved so the probabilities sum to 1.
  - Odds-ratio: p_i = r_i / (OR + r_i - OR*r_i).
  - Shin: models a share Z of insider money.
  - The vignette calls basic/multiplicative the least accurate method in the package. It notes that **with two outcomes, additive equals Shin**, and that additive can produce negative probabilities for longshots. — [implied R package vignette](https://ftp.fau.de/cran/web/packages/implied/vignettes/introduction.html)
- Buchdahl calls the equal-margin (multiplicative) method "crude and frankly inaccurate" and recommends the odds ratio, logarithmic (power), or Shin methods. — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- In a lopsided market the methods diverge mainly on the underdog side. One example gives a fair price of about 3.80 (proportional), about 4.00 (Shin) and about 4.13 (power). — [OddsPapi no-vig post](https://oddspapi.io/blog/?p=3089)
- **Line moves.** One documented "modelled closing line" design:
  - Count props use a Poisson distribution and continuous stats use a Normal.
  - It fits the distribution to the de-vigged probabilities across the line ladder, then evaluates it at the bet's line and side.
  - With only one line, it fits the location and takes dispersion from a prior table calibrated in backtesting. — [odds-api.io modelled closing line spec](https://docs.odds-api.io/superpowers/specs/2026-08-31-modelled-closing-line-design)
- **Benchmark choice.**
  - Pinnacle's close is widely used as the sharp benchmark (vendor and blog claims). — [SharpAPI CLV docs](https://docs.sharpapi.io/en/api-reference/historical-clv/)
  - Pinnacle reportedly closed public API access on July 23, 2025 (secondary source). — [thespread.com](https://www.thespread.com/?p=550721)
  - Unabated builds a vig-free consensus "Unabated Line" from the sharpest books. — [Dealroom profile](https://app.dealroom.co/companies/unabated_products)
  - For NFL props, Caesars and FanDuel are named as the most efficient US books. — [Establish The Run](https://establishtherun.com/understanding-the-current-ecosystem-of-nfl-player-props/)
- **Prop margins** are reported at about 6-8% for many prop markets, higher for alternate lines. This is a blog figure and unverified. — [Establish The Run](https://establishtherun.com/understanding-the-current-ecosystem-of-nfl-player-props/)
- **The Odds API data.**
  - Historical snapshots are at 5-minute intervals.
  - Player props are available from 2023-05-03 05:30 UTC.
  - The documented rate is 10 credits per region per market for historical data. — [The Odds API v4 docs](https://the-odds-api.com/liveapi/guides/v4/)

### Inferences (concrete recipe for this data)
1. **Benchmark close.** For each prop, build a consensus no-vig close: the median or mean of the de-vigged probabilities across all books quoting the same line at the closing snapshot. Use power or Shin (equal to additive for two outcomes) rather than multiplicative. Add Pinnacle (eu region) if the API returns NBA props for it; I did not verify whether it does. Also report CLV against FanDuel alone, and against the consensus without FanDuel, as a robustness check.
2. **Same line:** CLV = bet decimal odds x p_close(side) - 1, which is your expected value if the close is fair.
3. **Different line**, for example over 24.5 at open and closing line 25.5:
   - Fit a count distribution to the closing price: a negative binomial with the variance-to-mean ratio from the team's own projection residuals, or a Normal for PRA and points.
   - Solve for the mean that reproduces p_close(over 25.5), then evaluate P(over 24.5) under that distribution.
   - Integer-crossing matters. Moving from 24.5 to 25.5 shifts probability by P(X = 25), which for points is about 3-5 percentage points (inference from Poisson and NB shapes, not sourced).
   - Simpler fallback: restrict CLV to bets where the line number did not change, and separately report the share of bets where the line moved in your favor. Be aware this introduces selection bias.
4. **Closing snapshot timing.** Use the last snapshot before tip-off, for example tip minus 5 minutes, given 5-minute granularity. Late NBA scratches move props sharply, so a snapshot taken an hour before tip-off is not the close.
5. **Separate the injury-news component.** Report CLV split by whether a lineup or injury change occurred between bet time and close. If CLV comes only from bets where news broke in your favor, it reflects luck or timing, not model skill.

### Gaps
- No source quantified which book has the sharpest NBA *prop* close. The Caesars/FanDuel claim is about NFL props and is qualitative.
- Not verified whether The Odds API returns Pinnacle NBA player props in its historical data, or the exact per-event historical cost formula (the docs page section was truncated).
- No comparative accuracy study of de-vig methods specifically on two-way prop markets was found. The Clarke, Kovalchik and Ingram (2017) paper comparing methods could not be retrieved (403).

## 3. Test design: bet at an earlier snapshot and measure CLV against the close

### Takeaway
Re-run the existing 592 games using an earlier snapshot as the "bet" price (morning or opener) and a near-tip snapshot as the close. Pre-register a primary metric, mean CLV per bet against a consensus no-vig close, and test it with clustered standard errors. This answers whether the model has an edge in one season's data, which profit alone cannot do. Credit cost: about 2 extra snapshots x markets x 592 events x 10 credits.

### Cited Findings
- Snapshots are available every 5 minutes, and historical props go back to May 2023. The 2023-24 season can therefore serve as a holdout as well. — [The Odds API docs](https://the-odds-api.com/liveapi/guides/v4/)
- **Standard-error approach:** SE = s/sqrt(N); one-sided 95% uses z = 1.645. — [HowProsBet](https://howprosbet.com/how-to-verify-your-betting-edge/)
- **Line movement toward your side.** Buchdahl treats it as evidence: 756 of 952 +EV bets shortened or held. — [Pinnacle Odds Dropper / Buchdahl](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)
- **Originators.** They may show little CLV while still having an edge, so a null CLV result is not proof of no edge. — [same](https://www.pinnacleoddsdropper.com/blog/closing-line-value--clv-demystified-by-expert-joseph-buchdahl)

### Inferences (recommended design)
- **Snapshots per event:**
  - (a) morning, about 10:00 ET or the earliest snapshot with props posted;
  - (b) the existing T-60 minutes snapshot;
  - (c) close at T-5 minutes, or the last snapshot before commence_time.
  - Cost is 10 credits x markets x regions per snapshot. With 4 markets (PTS, REB, AST, PRA) and 1 region: 40 credits per snapshot, 592 x 2 new snapshots = about 47,000 credits. Adding a second region (eu, for Pinnacle) doubles that. This is my arithmetic from the stated pricing; check it against the actual billed cost on a small batch first.
- **Primary hypothesis:** mean CLV > 0 for model-selected bets taken at snapshot (a), measured against close (c). Secondary: the same for (b) versus (c). This shows whether the model anticipates movement or just reacts late.
- **Control or placebo:** compute CLV for *all* props, and for the side the model rejects. Mean CLV across all props should be about -vig/2. The model's picks should beat that baseline, not only beat zero.
- **Clustering:**
  - Props in the same game, and especially for the same player, are correlated. PTS and PRA for one player are nearly the same bet.
  - Use cluster-robust SEs by game, or a block bootstrap over games.
  - The effective N is closer to the number of games or player-games than to the number of bets.
- **Power with this data:**
  - Suppose about 770 bets in about 400 effective clusters, and a prop CLV SD of 0.15 (to be measured).
  - Then SE is about 0.15/sqrt(400), or about 0.75%. A 2% mean CLV would give z of about 2.7, which is detectable. A 1% mean CLV gives z of about 1.3, which is not.
  - Compare the profit test: SE is about 3.4% on the same sample.
- **Pre-register:** the decision threshold (for example, the lower 95% bound of mean CLV > 0), the de-vig method, the benchmark close, and the line-move handling. This matches the team's existing pre-registration practice.
- **Calibration cross-check:** if CLV is positive, also confirm that de-vigged closing probabilities are calibrated against outcomes for NBA props in this sample, so that CLV can be interpreted as expected value.

### Gaps
- There is no published empirical CLV SD for NBA props, so the power numbers above are illustrative until measured.
- There is no documented evidence on how often NBA prop lines are posted early (morning) in The Odds API data or how complete that coverage is.

## 4. Staking: Kelly, fractional Kelly, and correlated simultaneous props

### Takeaway
Full Kelly for a two-way prop is f* = edge / (decimal odds - 1). At -110, a 2% edge gives about 2.2% of bankroll and 3% gives about 3.3%. Use quarter Kelly or less, sized on CLV-estimated edge rather than raw model edge, because edge estimates are noisy and overbetting is far more costly than underbetting. Same-game and same-player props are correlated, so naive per-bet Kelly overbets. Treat each game, or each player, as one position: combine or cap correlated bets, and cap total simultaneous exposure.

### Cited Findings
- **Thorp's Kelly paper** has explicit sections on "the probability of ever being reduced to a fraction x of this initial bankroll" and "the case for 'fractional Kelly'", plus portfolio theory for simultaneous positions. I could only confirm the section titles, not the text. — [Thorp, The Kelly Criterion in Blackjack, Sports Betting, and the Stock Market (archived PDF)](https://wayback.archive-it.org/5456/20240920155724/https://www.eecs.harvard.edu/cs286r/courses/fall12/papers/Thorpe_KellyCriterion2007.pdf)
- **Fractional Kelly (secondary sources):**
  - Half Kelly gives up about 25% of the growth rate but halves the volatility of log-wealth.
  - The growth penalty for overbetting is severe, while underbetting costs little.
  - Under full Kelly, the chance of eventually halving the bankroll is about 1/2. — [LuxAlgo Kelly](https://www.luxalgo.com/library/concept/kelly-criterion/); [MetricGate](https://metricgate.com/docs/kelly-criterion/)
- **Simultaneous events.** Applying sequential Kelly fractions to overlapping games can commit more than the bankroll, so a joint optimization is needed. — [AUEB thesis](https://pyxida.aueb.gr/server/api/core/bitstreams/5b11b70b-f4fd-4894-860c-c17a2b8a847a/content)
  - Grant and Buchen (2012), simulating EPL 2007-08, found Kelly with multibets outperformed portfolio optimization on single bets. — [Grant & Buchen, J. Gambling Business & Economics](https://ideas.repec.org/a/buc/jgbeco/v6y2012i2p1-28.html)
  - Grant (2008) showed multibetting reproduces sequential Kelly when payouts are multiplicative. — [Decision Analysis](https://pubsonline.informs.org/doi/abs/10.1287/deca.1080.0106)
  - Both papers treat *independent* simultaneous games, not correlated outcomes.
- **Practitioner handling of correlation is ad hoc.**
  - DataGolf forum users cut the Kelly fraction when total exposure looks high and called this "Not a science at all". — [DataGolf forum](https://forum.datagolf.com/t/bet-sizing-kelly-criterion/43)
  - A calculator site suggests dividing by the number of concurrent bets and capping total exposure at about 25%. — [topendsports Kelly calculator](https://www.topendsports.com/sport/betting-tools/kelly-criterion-calculator.htm)
- **Same-game correlation is real.** Books price same-game parlays with correlation models, for example team scoring raising teammates' points props, and FanDuel models correlations among player outcomes. — [DeucesCracked SGP guide](https://www.deucescracked.com/blog/same-game-parlay-correlation-strategy); [Action Network SGP guide](https://www.actionnetwork.com/education/same-game-parlay-guide)

### Inferences (concrete staking rules)
- **Per-bet Kelly at -110:**
  - f* = (p x 1.91 - 1)/0.91. A 1% edge gives 1.1% of bankroll, 2% gives 2.2%, 3% gives 3.3%.
  - Quarter Kelly gives about 0.3% / 0.55% / 0.8% of bankroll per bet.
- **Drawdown risk, using the continuous-time approximation.** P(ever falling to x of bankroll) = x^(2/c - 1) for Kelly fraction c. This formula is the standard result I believe Thorp presents, but I could not verify it from the text. At the true edge:

  | Kelly fraction (c) | P(ever halving) | P(ever -30%) | Share of max growth |
  |---|---|---|---|
  | 1 (full) | 0.50 | 0.70 | 100% |
  | 1/2 | 0.125 | 0.34 | 75% |
  | 1/4 | about 0.008 | about 0.08 | about 44% |

  If the true edge is half the estimate, full Kelly is effectively 2x Kelly, which has about zero long-run growth. This is the strongest argument for quarter Kelly or less.
- **Correlated props, practical rule:**
  1. Never bet both PTS and PRA (or PTS+REB, PTS+AST) in the same direction on one player as separate full-size bets. Pick the one with the highest CLV or edge, or size the group as a single bet.
  2. Teammates' overs are mildly positively correlated through pace and game total. Opposite-team overs are also positively correlated through pace. A same-player PTS over with a teammate's PTS over is weakly negatively correlated through usage.
  3. Cap per-game exposure at 1-1.5x a single full stake, and cap total nightly exposure at about 10-15% of bankroll under quarter Kelly.
  4. For a principled version, estimate the joint outcome covariance from historical box scores (the team has the data). Then solve multi-bet Kelly numerically: maximize E[log(1 + sum f_i R_i)] over simulated joint outcomes for that night's slate. This is the "simultaneous Kelly" that the papers above formalize.
- **Size on shrunk edges.** Use the CLV-implied edge, or the model edge shrunk toward the market, rather than raw model edge. The 2024-25 test cannot reject zero edge, so the honest current Kelly stake is about zero until CLV confirms an edge.

### Gaps
- No source quantified correlations between NBA stat props (PTS/REB/AST/PRA, teammates). They must be estimated from the team's own box-score data.
- No peer-reviewed closed-form Kelly treatment for correlated sports bets was found. Numerical optimization is the standard approach (inference).
- The Thorp drawdown formula and half-Kelly figures are from my background knowledge plus secondary sources. The Thorp PDF text could not be extracted to confirm them.

## 5. Variance: realistic drawdowns and bets needed at a 1-3% edge

### Takeaway
At -110 with flat 1-unit stakes, even a true 2-3% edge has a 20-30% chance of showing a loss over one season of about 770 bets. Median peak-to-trough drawdowns run about 22-27 units, and the 90th percentile about 38-46 units. Proving a 2% edge from profit alone needs about 9,000-18,000 bets; CLV, if prop CLV SD is near 0.1-0.2, needs a few hundred.

### Cited Findings
- **Required N (profit test, 95% one-sided, no power requirement):** at odds 1.80, 2% edge needs about 5,400 bets and 3% about 2,400; at odds 2.00, 2% needs about 6,800 and 3% about 3,000. — [HowProsBet](https://howprosbet.com/how-to-verify-your-betting-edge/)
- **Long losing runs** of hundreds or thousands of bets are possible even with a real edge (Buchdahl's caution). — [football-data.co.uk](https://www.football-data.co.uk/blog/wisdom_of_the_crowd.php)

### Inferences
My own Monte Carlo: flat 1-unit stakes at decimal 1.91, independent bets, 2,000 simulations per cell.

| True edge | Bets | P(net loss) | Median max drawdown | 90th pct drawdown |
|---|---|---|---|---|
| 1% | 770 | 0.41 | 26.9u | 45.6u |
| 1% | 2,000 | 0.31 | 41.9u | 70.0u |
| 1% | 5,000 | 0.23 | 61.1u | 101.4u |
| 2% | 770 | 0.29 | 24.5u | 42.3u |
| 2% | 2,000 | 0.18 | 35.8u | 60.3u |
| 2% | 5,000 | 0.06 | 50.2u | 80.8u |
| 3% | 770 | 0.20 | 22.1u | 38.0u |
| 3% | 2,000 | 0.09 | 31.8u | 53.2u |
| 3% | 5,000 | 0.02 | 42.4u | 67.3u |

- **Bets needed** (two-sided alpha = 0.05, 80% power, per-bet SD 0.95): about 71,000 at 1%, 17,800 at 2%, 7,900 at 3%.
- **Correlation makes this worse.** Same-game positive correlation inflates variance, so real drawdowns and required N are larger than these independent-bet figures.
- **Bankroll implication.** With 1 unit = 0.5% of bankroll (about quarter Kelly at a 2% edge), a 45-unit 90th-percentile drawdown is about a 20% drawdown. Practitioners should plan for 20-25% drawdowns even when the edge is real.

### Gaps
- No published data on realized drawdowns of actual NBA prop bettors was found.
- The simulations assume independence and a constant price. Correlation and line-dependent odds would widen the drawdowns.
