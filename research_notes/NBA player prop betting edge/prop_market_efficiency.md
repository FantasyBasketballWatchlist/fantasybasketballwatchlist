# NBA Player Prop Market Efficiency and Documented Inefficiencies

Scope note: 17 search/fetch calls. The main finding is that **there is almost no peer-reviewed, data-driven study of NBA player prop market efficiency**. Nearly all academic work covers game spreads, totals and moneylines. Prop-specific evidence comes from practitioner writeups, mostly NFL-focused, and from vendor or affiliate content. Each item below is labelled by evidence quality.

## 1. What do academic and quantitative analyses find about prop market efficiency, compared with game spreads and totals? Is there evidence of over/under bias, favourite-longshot bias, or systematic mispricing?

### Takeaway
No rigorous published test of NBA prop efficiency or prop over/under bias turned up. The closest academic evidence is on game **totals**. There, bettors over-bet overs, especially on high totals, but NBA totals were still roughly efficient: betting unders did not reliably beat the vig. Practitioners widely claim that unders and skewed distributions favour the under side in props, but nobody has tested this rigorously in public.

### Cited Findings
- **Game totals, NBA (academic, older).** Paul and Weinbach found that overs are over-bet across NFL, college football, arena football and NBA totals markets. Using actual sportsbook volume, the share bet on the over rises with each point of the total. [Paul & Weinbach 2005, J. Economics & Finance](https://link.springer.com/article/10.1007/BF02761585); [IDEAS listing](https://ideas.repec.org/a/spr/jecfin/v29y2005i3p409-415.html). These are pre-2018 sources.
- A re-examination of NBA 2000-01 to 2007-08 concluded that both spread and totals markets were efficient. It found a pattern of over-betting the over in high-total games (totals above 200) that grows as the total rises, but not one strong enough to profit from. Unlike the NFL, fading public sentiment in the NBA did not win more often than efficiency implies. [The Sport Journal, "NBA Gambling Inefficiencies: A Second Look"](https://thesportjournal.org/article/nba-gambling-inefficiencies-a-second-look/) (older data)
- **NFL totals:** betting every under won 50.4% from 1995 to 2004, which is below the roughly 52.4% break-even at -110. The authors call the market "remarkably efficient". This is NFL data and an older source. [Kochman & Goodwin via Syracuse repository](https://surface.syr.edu/researchcenter/5) (summarised from the search snippet; full text not reviewed)
- **NBA spreads, recent multi-book data:** a thesis using 10 online sportsbooks found profitable strategies, and the profits were larger at lower-margin books. This again shows that price and margin dominate. [Lust, Miami University thesis](https://etd.ohiolink.edu/acprod/odb_etd/ws/send_file/send?accession=miami1533158563565605&disposition=inline) (snippet only)
- **NBA COVID-era inefficiency:** the NBA showed large betting-market inefficiencies during COVID-19 (no-fan games), while other leagues' markets stayed efficient. This concerns moneylines, not props. [arXiv 2109.07581](https://arxiv.org/pdf/2109.07581)
- **The only prop-specific academic item found** is Wornow (2026), a Claremont McKenna senior thesis. It covers FanDuel **closing** prop lines for 178 NBA players across five stat categories, 2022 to 2025. Using staggered state mobile-betting legalization in a difference-in-differences design, it finds a larger absolute deviation of outcomes from the closing line in legal states (coefficients about 0.27 to 0.40; points 0.665, p=0.02). It finds **no consistent directional (over/under) bias**. It is campus-only, so only the abstract and metadata were reviewed, and it is an undergraduate thesis, not peer-reviewed. [Claremont scholarship](https://scholarship.claremont.edu/cmc_theses/4171)
- **Median-anchored lines.** Unabated says that "Prop lines are set somewhere around a player's median performance." For right-skewed stats the mean sits above the median. Their example is a player with a 60.4-yard mean against a line of about 47.5. [Unabated, "Introducing Market-Based Prop Projections" (Oct 2026)](https://unabated.com/articles/introducing-market-based-prop-projections)
- **Public preference for overs (practitioner and journalist claim).** Bettors generally dislike unders, so books shade lines up to attract under money. Peabody's team bets mostly unders, and he advises over bettors to bet early and under bettors to wait. This comes from the narrator of a Super Bowl props podcast and is NFL-focused. [The Ringer, Gamblers S1E3](https://www.theringer.com/2022/09/28/pop-culture/gamblers-super-bowl-episode-3-rufus-peabody)
- **Anecdotal under/over hit rates (weak).** One bettor's Substack reported unders going 63.7% over 175 bets in one season and 33.3% over 36 bets in a later stretch. [Stealing Lines](https://stealinglines.substack.com/p/finding-a-flaw-in-the-process-best). A vendor blog says overs hit 46% at main lines in its own graded sample. [nbabettingsystem.com](https://nbabettingsystem.com/strategy/). Both samples are small or self-graded.
- **Graded model results from a prediction site (vendor, weak).** Its top-tier points picks hit 50.5% over 917 plays, which it calls a coin flip that loses to the vig. Its assists picks hit 56.8% over 791. [Prediction Engine](https://predictionengine.app/learn/nba-player-props-guide)
- **Conflicting media claims about points props.** Some guides say props are much less efficient because they attract less sharp action. [nbabettingsystem.com](https://nbabettingsystem.com/articles/nba-betting-market-efficiency/). Others say points props are the *most* efficiently priced prop. [OddsIndex](https://oddsindex.com/guides/nba-player-props-guide). Action Network says props are easier to beat than sides and totals, and that their limits are lower, which draws fewer sharps. [Action Network NBA props](https://www.actionnetwork.com/nba/props)
- **Favourite-longshot bias in props:** no NBA-prop-specific study was found. One relevant structural note is that FanDuel often posts **one-way** prop markets, such as a home run at +200 with no "no" side. That allows large holds on the longshot side. [BetSmart, "Efficient Prop Markets" (Jul 2025)](https://betsmart.beehiiv.com/p/efficient-prop-markets)

### Inferences
- The team's result (book no-vig Brier 0.247 against the model's 0.255, and roughly -1.8% at median prices) is consistent with what little evidence exists. Main-line points, rebounds and assists props at the close are hard to beat, and the over-bias in game totals has historically been too small to clear the vig.
- If lines are anchored near the median and the public prefers overs, any structural edge should sit on **unders**, particularly for right-skewed, high-variance stats such as threes, role-player points, and blowout-sensitive minutes. The practitioner behaviour of Peabody's team betting mostly unders fits this. However, this has not been publicly established for NBA props, so it is a hypothesis to test on the team's own data (over versus under ROI split, by stat and by line size).
- The Lust thesis suggests that margin reduction (best price) matters as much as model skill. This matches the team's finding that best-price shopping moved them from about -1.8% to break-even.

### Gaps
- No peer-reviewed, multi-season study of NBA prop over/under bias, calibration of book probabilities, or favourite-longshot bias by line or odds level was found. The Wornow thesis full text was inaccessible.
- No quantitative comparison of prop closing-line efficiency against spread or total efficiency, such as Brier or log-loss by market, was found.

## 2. Opening versus closing line efficiency for props: when are lines softest, and how much do they move?

### Takeaway
Practitioners agree that prop openers and lines that are stale after news are softer than closers, and that books cap limits during "price discovery". But no published quantification of NBA prop line movement from open to close turned up. Leading sharps describe a shift away from hammering openers as prop markets have become more efficient.

### Cited Findings
- Peabody, a leading prop bettor, said Super Bowl props have "gotten a lot more efficient." [Fox Sports (Feb 2022)](https://www.foxsports.com/stories/nfl/super-bowl-2022-odds-pro-bet). By 2026 he reportedly no longer rushes opening numbers. He waits for the market to develop and then targets mispriced props, **alt lines**, and game-script scenarios that aren't priced correctly. [VSiN Daily (Feb 4, 2026)](https://vsin.com/the-vsin-daily/inside-the-mind-of-sharpest-of-the-super-bowl-prop-sharps/) (secondhand summary; NFL)
- FanDuel starts props at "not-terribly-high limits" during price discovery, with "usually respectable limits" closer to game time. Caesars took at least $500 from sharp accounts even on openers, moved aggressively on action and sometimes overreacted, so fading its initial move could yield good prices. [Establish The Run, Jack Miller (Aug 2023)](https://establishtherun.com/understanding-the-current-ecosystem-of-nfl-player-props/) (NFL)
- **Injury news:** when a starter is ruled out late, sportsbooks adjust the backup's prop in about 15 seconds, while pick'em sites may leave it up for minutes. [4for4, Connor Allen (Jun 2023)](https://www.4for4.com/2023/preseason/how-win-money-playing-pick-em-sites)
- An NBA bettor describes a recurring pattern after news drops: the line moves, then reverts "somewhere in the middle". He argues an edge comes from anticipating injury reports or fading overreactions. [Fiddles Picks Substack](https://fiddlespicks.substack.com/p/navigating-nba-injury-news-with-an) (anecdotal)
- Unabated's market-based projections weight books with more recent moves more heavily, because "some books update slower than others, which can create edges against them." [Unabated (Oct 2026)](https://unabated.com/articles/introducing-market-based-prop-projections)

### Inferences
- The team's snapshot taken one hour before tip is close to the close, which is the hardest point to beat. The documented soft windows are openers or price discovery (low limits) and the minutes after injury or lineup news, especially at slow books and on pick'em apps. A projection model that does not react to news within minutes is structurally positioned in the least favourable window.
- A natural next test is to compare the model against **opening** lines and measure closing-line value (CLV) rather than results. This needs timestamped line history.

### Gaps
- No dataset or study quantifying the average absolute move from open to close for NBA props, or the CLV of models, was found.
- No evidence was found on the times of day when NBA prop lines are typically posted by each book.

## 3. Which prop types, player types and books are softest? Which books are market makers and which follow?

### Takeaway
Unlike game lines, **there is no consensus sharp "source of truth" book for props**. Pinnacle, Circa and Betcris make markets on sides and totals but post thin prop menus. Among US books, FanDuel and Caesars are most often named as the sharpest prop originators. Several books share outsourced feeds, so groups of books move together. Claims about the "softest prop type" conflict and are mostly unsourced.

### Cited Findings
- Pinnacle, Betcris and Circa are the market makers for game lines but "not the sharpest books for props", because they post limited prop sheets late. The "top-down" method of devigging one sharp book "isn't really possible with props." Caesars and FanDuel are "likely the two standouts" domestically. FanDuel sets its own numbers. MGM and Caesars reportedly outsource origination from the same source. Many offshore books use the same line-setting tool. [Establish The Run (Aug 2023)](https://establishtherun.com/understanding-the-current-ecosystem-of-nfl-player-props/) (NFL)
- "The jury is still out as to which, if any, books are truly sharp for props." Prop markets are less liquid than main markets. [Unabated (Oct 2026)](https://unabated.com/articles/introducing-market-based-prop-projections)
- FanDuel is "more of a source of truth" for props than some sharper books, because of its large customer base. The source warns that the sharpest FanDuel market differs by sport and needs backtesting, and that props have gone "from one of the easiest markets to beat to an efficient market" as handle grew. [BetSmart (Jul 2025)](https://betsmart.beehiiv.com/p/efficient-prop-markets) (newsletter promoting a tool; qualitative)
- Prop limits are lower than spread and total limits, and sharp accounts get restricted faster on props. [BetSmart](https://betsmart.beehiiv.com/p/efficient-prop-markets); [Legal Sports Report](https://www.legalsportsreport.com/180810/could-nba-try-to-limit-betting-on-player-props-after-porter-ban/)
- **Regulatory change (Oct 2026):** the NBA and major sportsbooks agreed to remove certain player prop bets, including parlays on the under for multiple stats of the same player, after betting-integrity scandals. They are also reviewing prop limits. [Deseret News (Oct 16, 2026)](https://www.deseret.com/sports/2026/10/16/nba-sportsbooks-agree-to-ban-several-types-of-player-prop-bets-amid-gambling-concerns/); [Covers (Oct 31, 2025)](https://www.covers.com/industry/sportsbooks-reportedly-working-with-nba-on-prop-markets-following-scandal-oct-31-2025)
- **Prop margin estimates conflict.** Estimates range from about 3% at sharp or low-margin books to 7% or more at recreational books [oddsguy.ai](https://oddsguy.ai/learn/hold), 8 to 12% on mid-tier NBA games (a betting-tips page), and 12 to 18% "operator hold" from affiliate marketing. [track360.io](https://track360.io/blog/prop-betting-affiliate-strategy-operator-margin-guide-2026). The higher figures probably mix up actual hold (gross revenue divided by handle) with two-sided overround, so treat them as unreliable.
- On player types and prop types, the claim that role players and low-volume props are softer appears only in unsourced vendor guides. [nbabettingsystem.com](https://nbabettingsystem.com/strategy/); [Action Network](https://www.actionnetwork.com/education/how-injuries-affect-betting-lines-a-guide-to-market-movement) (teammates "pick up the slack" when a high-volume player is out, which it calls a "hidden value" area)

### Inferences
- The team's measured two-sided margin of about 6.8% at median prices and about 3.5% at best price sits inside the credible 3 to 7%+ range.
- Because there is no single sharp prop book, a **consensus no-vig blend across books** (as Unabated builds) is likely a better benchmark than any one book. The finding that book no-vig probabilities beat the model's Brier score probably understates how sharp the full market is. A model edge should be measured against the multi-book consensus.
- The October 2026 removal of some prop types and the scrutiny of limits may reduce available liquidity in exactly the niche props that are softest.

### Gaps
- No quantitative ranking of NBA prop types (points, rebounds, assists, threes, PRA) by closing efficiency or hold was found.
- No data on stars versus role players was found. The claim that role players are softer is unsupported anecdote.
- Book origination relationships come from 2023 NFL commentary. Current NBA-specific feed sharing between books (for example, which books use Kambi, OpenBet or in-house pricing for NBA props) was not verified.

## 4. DFS pick'em (PrizePicks, Underdog, Sleeper, Pick6): inefficiencies, stale lines, break-even rates, and how sharps exploit them

### Takeaway
Pick'em apps charge roughly -115 to -137 per leg, depending on entry type. That means per-leg break-evens of about 54% to 58%, a higher bar than sportsbook -110. Their structural weaknesses are **slow-moving or static lines** (DraftKings Pick6 lines don't move once set) and **payouts that ignore correlation**. Sharps exploit these by comparing pick'em lines with a devigged sportsbook consensus and by acting on news faster than the apps.

### Cited Findings
- **PrizePicks implied per-leg price:**
  - 2-pick Power (3x): about -137, a 57.7% per-leg break-even.
  - 5-pick Flex (10x / 2x / 0.4x): about -119, roughly a 54% break-even.
  - 6-pick Flex: about -118.
  - 5-pick Power: about -122. 6-pick Power (37.5x): about -121.

  Sources: [Action Network](https://www.actionnetwork.com/education/prizepicks-flex-play-or-power-play-math); [BettingPros](https://www.bettingpros.com/articles/how-to-make-money-on-prizepicks-picking-the-right-slip-size-props/); [Stokastic](https://www.stokastic.com/articles/dfs-strategy/how-prizepicks-multipliers-work). Payouts vary by state and promotion. Another model puts the 5-pick break-even at 54.9% (-122).
- **Underdog implied per-leg price:** 5-pick Flex about -121, 6-pick Flex about -117, 2-pick Standard about -115 (the best Underdog price). Same sources as above. A 2-leg Underdog entry is equivalent to -136 per leg, about 8.42% vig, under 2023 payouts. [4for4 (Jun 2023)](https://www.4for4.com/2023/preseason/how-win-money-playing-pick-em-sites). The WebFetch summary of 4for4's insurance break-even numbers was garbled ("16.81%" and "61.58%"), so they are omitted as unreliable.
- **Stale lines:** pick'em apps "generally move a bit slower than sportsbooks" and "likely won't limit you" for betting stale lines. In NFL examples, apps left QB and receiver lines unchanged before a heavy-rain game while books cut them by 25+ yards, and posted lines for players expected to sit. Pick'em lines are often 5 to 10% off sportsbook lines, though "this doesn't automatically make a bet good." Limits were about $250 to $500 per site. [4for4 (Jun 2023)](https://www.4for4.com/2023/preseason/how-win-money-playing-pick-em-sites)
- **DraftKings Pick6:** lines don't move once set, so they can go stale against the market. [Unabated (Oct 2026)](https://unabated.com/articles/introducing-market-based-prop-projections)
- **Correlation:** Underdog pays the same regardless of which side you pick, so correlated legs (for example, a QB over plus his WR over) don't lower the payout. Sportsbooks price correlation in same-game parlays. [4for4](https://www.4for4.com/2023/preseason/how-win-money-playing-pick-em-sites)
- Underdog is called the "sharper" site, with lines that tend to move toward Underdog's projection, which is the basis for finding PrizePicks value. [FTN Fantasy](https://ftnfantasy.com/?p=104476) (search snippet; opinion)
- PrizePicks offers "demon" and "goblin" alternate lines with altered payouts. Only its standard line is comparable to Underdog's balanced line. [Apify scraper description](https://apify.com/lergassy/dfs-props-scraper)
- Vendors sell tools that compare PrizePicks lines with Pinnacle or consensus no-vig odds to flag +EV picks. [SharpAPI](https://sharpapi.io/sportsbooks/prizepicks-odds-api); [BettingPros optimizers](https://www.bettingpros.com/articles/bettingpros-launches-new-prizepicks-and-underdog-optimizers/) (vendor marketing)

### Inferences
- With book no-vig probabilities better calibrated than the model, the model cannot clear a 54 to 58% per-leg break-even on its own. A pick'em strategy only works by **sniping lines that are off-market against a sharp consensus** (stale or news-driven), not by projecting.
- The model's value in pick'em would be secondary: as a tiebreaker or filter among already off-market lines.

### Gaps
- No independent, audited study of pick'em player profitability, or of how PrizePicks and Underdog restrict or ban winners, was found.
- Current (2026) payout tables and state restrictions were not verified directly, and pick'em legality varies by state.

## 5. Realistic edges and ROI reported by credible sharp prop bettors, and how they measure it

### Takeaway
Credible sharps measure skill by **closing-line value (CLV) against a devigged market consensus**, not by short-run win-loss records. Public sharp sources give almost no specific prop ROI figures. What they emphasise instead is that the prop edge has shrunk and now lives in niche spots: alt lines, game-script pricing, news speed, and best-price shopping. Low limits cap profitability.

### Cited Findings
- CLV is the standard yardstick for whether a bet beat the market, as defined in Action Network's daily prop columns. Those columns' own results are self-reported and unaudited. [Action Network](https://www.actionnetwork.com/education/how-injuries-affect-betting-lines-a-guide-to-market-movement)
- Peabody (Unabated co-founder) built statistical models, and his edge also comes from spotting when a book "hangs a bad number". [Fox Sports (2022)](https://www.foxsports.com/stories/nfl/super-bowl-2022-odds-pro-bet). His current approach targets alt lines and game-script mispricing. No ROI numbers are given. [VSiN (Feb 2026)](https://vsin.com/the-vsin-daily/inside-the-mind-of-sharpest-of-the-super-bowl-prop-sharps/)
- Unabated tells bettors to use the market consensus as "one of your blended sources of truth" rather than relying on a model alone. [Unabated (Oct 2026)](https://unabated.com/articles/introducing-market-based-prop-projections)
- Props "went from one of the easiest markets to beat to an efficient market", and sharps get limited quickly on props. [BetSmart (Jul 2025)](https://betsmart.beehiiv.com/p/efficient-prop-markets)
- In academic ML betting research, choosing models by **calibration** rather than accuracy produced higher returns, and Kelly staking only works with a well-calibrated model. [Walsh & Joshi, Machine Learning with Applications (2024)](https://www.sciencedirect.com/science/article/pii/S266682702400015X); [arXiv 2303.06021](https://arxiv.org/pdf/2303.06021) (NBA game outcomes, not props)
- A 2019 single-season NBA study found that profits were achievable only with expert video-derived features, while models built on box-score statistics lost significantly. [ResearchGate, "Exploiting sports-betting market using machine learning"](https://www.researchgate.net/publication/331218530_Exploiting_sports-betting_market_using_machine_learning) (game outcomes; summarised from a search snippet)

### Inferences
- The fact that box-score models lose to the market in NBA game betting closely matches the team's projection model losing to prop lines. Public-data projections are already priced in.
- Realistic sharp prop edges, where they exist, are probably low single-digit percentages on low limits. This is an inference: no credible public source states a number. Given the team's best-price result of roughly break-even, with an interval that easily includes negative values, the evidence does not support a positive edge. Any edge claim would need CLV against a multi-book no-vig close.
- Directions most consistent with what sharps describe:
  - Earlier lines or news timing, rather than the close one hour before tip.
  - An unders and skew focus.
  - Alt lines and game-script props.
  - Off-market pick'em or stale books measured against consensus.
  - Using the model as one input blended with the market, not a standalone source of truth.

### Gaps
- No credible public source gave audited ROI or CLV statistics for NBA prop betting. Peabody, Andrews and other sharps discuss method but not numbers in the sources found.
- Podcasts and full interviews (Establish The Run episode 67, Gambling With an Edge with Andrews and Peabody) were not transcribed or reviewed: [ETR ep. 67](https://establishtherun.com/episode-67-one-on-one-with-pro-sports-bettor-rufus-peabody/); [LVA podcast](https://www.lasvegasadvisor.com/gambling-with-an-edge/podcast-captain-jack-andrews-and-rufus-peabody-part-2/).
