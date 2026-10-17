# Fantasy Basketball Draft Tools (research date: 2026-09-29)

Context: the user's app already has a live draft tracker with manual clicks, snake order, ESPN positions, lineup-need and scarcity alerts, a suggested pick and live team rankings. These notes focus on what competitors do beyond that.

Caveats on sources: Reddit was not reachable through search. A query aimed at r/fantasybball returned only App Store and AlternativeTo pages, so user sentiment below comes from vendor help docs and is thin. Several FantasyPros support pages returned 403 and the product landing page returned 404, so some FantasyPros claims rely on search-result snippets of those pages (marked "snippet"). Some FantasyPros methodology text comes from football or baseball pages, and I assume it applies to NBA (marked).

## Q1: What does each tool do, what does it cost, and what does it support (points/cats, auction/snake, keeper/dynasty)?

### Takeaway
FantasyPros Draft Wizard is the most complete cross-platform suite: mock sims, live sync, a "Pick Predictor" showing availability %, projected standings and grades, and keeper sync. Its live assistant is paywalled at MVP tier and above. Basketball Monster and Hashtag Basketball are the basketball-specific category-league tools: dynamic values, categorical scarcity, projected standings, and punt-aware auction values. Hashtag charges very little. The host platforms (ESPN, Yahoo, Sleeper) offer mock lobbies, practice drafts and draft boards, but I found little intelligence in them.

### Cited Findings
**FantasyPros Draft Wizard (NBA)**
- Features listed on the NBA draft-software page: Pick Predictor ("See the % odds that players will still be available at your next pick"), live draft sync ("pick suggestions & auto-tracking of taken players"), Projected Standings plus grades for mock and real drafts, keeper sync ("Sync your keepers for use in the entire suite"), custom league-settings mocks, cheat sheets from "60+ fantasy basketball experts", player tags, and a "Redo" option for mock picks to test strategies. The page does not say whether auction or points leagues are supported. — [FantasyPros NBA Draft Software](https://draftwizard.fantasypros.com/basketball/draft-software/)
- Supported hosts for basketball: Yahoo, ESPN, Sleeper, CBS, Fantrax, FleaFlicker (snippet). — [FantasyPros support: supported hosts](https://support.fantasypros.com/hc/en-us/articles/26542048427291-Which-fantasy-basketball-league-commissioner-host-sites-are-supported-in-the-Draft-Wizard-Draft-Assistant)
- How sync works: ESPN needs the FantasyPros Chrome extension, with the host draft room open in one tab and the Draft Assistant w/ Sync in another tab of the same browser. Yahoo leagues usually can't be connected until 30 minutes before the draft (snippet). There is also a separate "Manual Draft Assistant", where the user marks picks by hand. — [FantasyPros support: launch Draft Assistant w/ Sync](https://support.fantasypros.com/hc/en-us/articles/115001362308-How-do-I-launch-the-Draft-Assistant-w-Sync-to-connect-to-my-draft); [Manual vs Sync](https://support.fantasypros.com/hc/en-us/articles/115001356148-What-is-the-difference-between-the-Manual-Draft-Assistant-and-Draft-Assistant-w-Sync)
  - Conflict: an older App Store listing says ESPN leagues "can be imported but only manual draft assistant is supported." It is probably outdated, since current support docs describe ESPN sync through the Chrome extension. — [App Store listing (snippet)](https://apps.apple.com/us/app/fantasy-football-draft-wizard/id1132708558)
- A mobile-app ESPN sync troubleshooting article exists, which suggests ESPN sync on mobile is a known pain point. — [FantasyPros support: mobile ESPN sync](https://support.fantasypros.com/hc/en-us/articles/115004245367-Why-won-t-the-FantasyPros-mobile-app-sync-with-my-ESPN-draft)
- Pricing: both Draft Assistant variants require MVP, HOF or GOAT. PRO does not include them. MVP includes 10 live draft syncs and HOF includes 50 (snippet). Quoted prices: PRO $11.99/mo, MVP $16.99/mo, HOF $22.99/mo monthly; annual works out to about $3.99, $5.99 and $8.99/mo. These prices came from search snippets of plan pages that may be football-specific, so treat them as approximate for NBA. — [FantasyPros: Draft Assistant cost](https://support.fantasypros.com/hc/en-us/articles/115001362188-How-much-does-the-Draft-Assistant-cost); [plans FAQ](https://support.fantasypros.com/hc/en-us/articles/25996886459931-How-much-do-your-premium-subscriptions-cost-What-plans-do-you-offer)
- Draft Intel (2023 blog, football context) feeds league-mates' past drafting tendencies into mock-draft bots. It needs Yahoo, ESPN or Sleeper and at least 2 years of draft history. Mock bots' "Draft Against" logic is customizable. — [FantasyPros blog 2023-08-22](https://blog.fantasypros.com/08-22-2023-making-the-most-of-the-mock-draft-simulator/)

**Basketball Monster**
- Draft Tracker has live connectivity with Yahoo, ESPN and CBS. Other hosts use "offline mode", where the user assigns players manually. Features: DynV, "overall value relative to remaining players at the time of a refresh... adjusts player values based on which players - more specifically, what stats - have been removed from the available draft pool"; Projected Standings; team Summary "vs Top Players" and "vs Drafted" (the latter "carrying more weight throughout the draft"); Categorical Scarcity (what stats remain in the pool); Positional Value (PosV). — [Basketball Monster Draft Tracker Tutorials](https://basketballmonster.com/drafttrackertutorials.aspx)
- The site describes tools for Yahoo, ESPN, FanTrax and CBS leagues, and its draft tracker imports from them for live projected standings (snippet). — [Basketball Monster FAQ](https://basketballmonster.com/Help.aspx)

**Hashtag Basketball**
- Auction value generator inputs: budget ($100–400), league size (6–30), roster size (10–20), minimum GP, "Standard/H2H/Minus 1" valuation types, a GP penalty (10–30%), and 16 selectable categories each with a 0.25x–3x multiplier (this is how punting is supported). Full values plus premium Yahoo/ESPN/Fantrax tools cost $2.50/mo on Patreon. The page gives no methodology. — [Hashtag Basketball Auction Values](https://hashtagbasketball.com/fantasy-basketball-auction-values)
- Premium tools (Patreon) include a Mock Draft Simulator and a Draft Tracker. Supports Yahoo, ESPN, Fantrax and Sleeper leagues (snippet). — [Hashtag Basketball home](https://hashtagbasketball.com/)
- Dynasty trade calculator blends Hashtag's dynasty rankings with crowdsourced rankings (snippet). — [Hashtag Dynasty Trade Calculator](https://hashtagbasketball.com/dynasty-trade-calculator)

**Host platforms**
- ESPN (2024-25): a new "modernized draft board view" shows every team's picks on one screen, color-coded by position (app only). "Practice Draft" runs a mock against computer managers using your own league's settings. League managers can edit draft type, order and time in the app. The article mentions no draft grades, keeper tools or recap. — [ESPN new features 2024](https://www.espn.com/fantasy/basketball/story/_/id/41532734/2024-fantasy-basketball-draft-board-new-features-espn)
- ESPN mock lobby: auction or snake, category or roto, 10/12/16/18 teams; nomination queue. — [ESPN Mock Draft Lobby](https://fantasy.espn.com/basketball/mockdraftlobby); [ESPN support](https://support.espn.com/hc/en-us/articles/4669696015124-Mock-Draft-Lobby)
- Yahoo: 24/7 live mock drafts where you choose league size, type and draft slot. — [Yahoo mock lobby](https://basketball.fantasysports.yahoo.com/nba/mock_lobby)
- Sleeper: snake, linear and auction drafts. Auction works in redraft, keeper and dynasty, with custom budgets per manager and nomination/bid timers up to 8–24h for slow drafts. Mock draftboards accept custom ADP, can be edited to set keepers before the draft, and can be copied as templates. — [Sleeper basketball](https://sleeper.com/fantasy-basketball); [Sleeper auction support](https://support.sleeper.com/en/articles/4056268-do-you-support-auction-drafts); [Sleeper auction blog](https://sleeper.com/blog/auction-draft/)

**Other tools**
- Lineup Experts: free, configurable NBA mock draft simulator with unlimited drafts, plus a free auction/salary-cap value generator. — [Lineup Experts mock sim](https://www.lineupexperts.com/basketball/mock-draft-simulator); [auction generator](https://www.lineupexperts.com/basketball/auction-value-generator)
- RotoBaller: free mock draft assistant with scoring presets from popular platforms, draft-type choice, dynasty keeper selections and roster limits (snippet). — [RotoBaller mock sim](https://www.rotoballer.com/fantasy-basketball-mock-draft-simulator)
- FantasySP: ADP from competitive leagues, plus auction MIN/MAX/AVG bids normalized to $200 (snippet). — [FantasySP ADP](https://www.fantasysp.com/average-draft-position/basketball)
- RotoWire: expert auction values for 2026-27, said to factor in production, position scarcity, team role and category impact (snippet). — [RotoWire auction values](https://www.rotowire.com/basketball/auction-values.php)
- Dynatyze: NBA dynasty trade calculator with A–F grades, 9-cat and points settings, and draft-pick values (snippet). — [Dynatyze](https://dynatyze.com/nba-trade-calculator)

### Inferences
- Live sync is the main paywall feature (FantasyPros MVP+). A free app that can pull ESPN/Yahoo draft state, for example by polling the league API after each pick, would undercut it. The user's app currently relies on manual clicks.
- The basketball-native differentiators are category-aware: DynV that recomputes value as *stats* leave the pool, categorical scarcity, and punt multipliers. The user's app runs scarcity alerts on positions. Scarcity by stat category, or by fantasy points for points leagues, is the analog to add.
- Host platforms offer almost no recommendation intelligence. The value third-party tools add is analytics, not the draft room itself.

### Gaps
- I could not confirm NBA-specific pricing for Basketball Monster, or whether the FantasyPros prices above apply to the NBA plan.
- I found nothing on Fantrax's or RotoWire's live draft assistants for NBA.
- I couldn't verify whether FantasyPros NBA supports auction live sync or points leagues. The NBA pages don't say.

## Q2: What features do users value most in live draft assistants, and what do they complain about?

### Takeaway
Judging by what vendors emphasize and put behind paywalls, the valued features are: automatic tracking of taken players, pick suggestions based on need, % availability at your next pick, projected standings and grades after the draft, and mock-bot modeling of real league-mates. Complaints I could document are all about sync reliability ("Waiting for draft sync", ESPN mobile, Yahoo's 30-minute window). I could not reach direct user sentiment from Reddit.

### Cited Findings
- FantasyPros markets the assistant as "pick-by-pick suggestions along with a monitor of your team needs" (snippet). — [FantasyPros Draft Assistant](https://draftwizard.fantasypros.com/basketball/draft-assistant/)
- The Pick Predictor can look 1, 2 or 3 rounds ahead. The worked example contrasts "<50% chance" of a player going next round with ">90%" further out, as a way to decide when to reach. — [FantasyPros blog 2023](https://blog.fantasypros.com/08-22-2023-making-the-most-of-the-mock-draft-simulator/)
- Post-draft Draft Analyzer gives an "instant report card": projected standings, team rankings, positional ranks, "steals and reaches", and improvement feedback. — [FantasyPros blog 2023](https://blog.fantasypros.com/08-22-2023-making-the-most-of-the-mock-draft-simulator/); [NBA Draft Analyzer](https://draftwizard.fantasypros.com/basketball/draft-analyzer/)
- Documented sync failure: FantasyPros keeps a help article for the error "Waiting for draft sync..." during live ESPN/Yahoo/Sleeper drafts. — [FantasyPros support](https://support.fantasypros.com/hc/en-us/articles/28876394605339--Waiting-for-draft-sync-error-message-how-to-fix-during-a-live-draft-ESPN-Yahoo-Sleeper-etc)
- Sync constraints: ESPN requires a Chrome extension and two tabs; Yahoo connects only about 30 minutes before the draft (snippet). — [FantasyPros launch article](https://support.fantasypros.com/hc/en-us/articles/115001362308-How-do-I-launch-the-Draft-Assistant-w-Sync-to-connect-to-my-draft)
- DraftKick's suggested decision thresholds: wait if availability is about 60–70% or higher, draft now if it is about 20–30% or lower. — [DraftKick 2023-01-09](https://draftkick.com/blog/projected-availability/)
- Basketball Monster says comparing against *drafted* players, rather than the top players overall, "carries more weight throughout the draft". — [Basketball Monster tutorials](https://basketballmonster.com/drafttrackertutorials.aspx)

### Inferences
- The user already has need and scarcity alerts, a suggested pick and live rankings. The most-marketed features they lack are (1) availability odds at the next pick, (2) projected standings and grades for categories or points, (3) a post-draft report with steals and reaches versus ADP, and (4) auto-sync.
- A manual-click tracker avoids the sync fragility users run into with extension-based tools, but it costs the user effort during the draft. Offering an optional import of picks from the league API, with manual entry as the fallback, gets the benefit of both.

### Gaps
- There is no first-hand user sentiment (Reddit or app reviews) specific to basketball draft assistants. The App Store page fetch returned 404.

## Q3: How do the best tools compute pick recommendations and "chance a player is available at your next pick"?

### Takeaway
There are two families. The simple one uses a normal CDF on ADP with a standard deviation: the real SD where available, otherwise ADP/4 or the range rule, (max−min)/4. The sophisticated one (FantasyPros) runs Monte-Carlo-style simulation of each opponent, drawing from a mix of expert cheat sheets and applying in-draft logic for team needs and position scarcity. Values are typically z-scores (categories) or points above replacement, converted to dollars so that a replacement-level player is worth $1. Inflation is money left in the room divided by value left on the board.

### Cited Findings
- **ADP normal approximation:** P(taken before pick X) = NORM.DIST(X, mean=ADP, sd); availability = 1 − that. DraftKick approximates sd = ADP/4, based on the observation that the min-to-max pick range is about ADP. The author calls the result "a (very) rough percentage" and shows availability at the user's next two picks. — [DraftKick, 2023-01-09](https://draftkick.com/blog/projected-availability/)
- FanGraphs workbook (2017): uses Excel's normal distribution with NFBC ADP and an SD estimated by the "Range Rule" (from min and max picks). You enter league size and draft slot, and it outputs the probability that a player is gone by each of your picks. — [FanGraphs ADP Availability Workbook, 2017-01-24](https://fantasy.fangraphs.com/adp-availability-workbook/)
- **Simulation approach (FantasyPros, football/baseball pages, assumed to apply to NBA):** bots don't simply follow ADP. They "leverage numerous expert cheat sheets to match the variety of drafters" and apply "in-draft pick logic based on team needs and position scarcity" to predict each team's pick. The Pick Predictor then reports % odds that a player survives to your next pick (snippet). — [FantasyPros NFL draft software](https://draftwizard.fantasypros.com/football/draft-software/); [FantasyPros 2017 Draft Wizard guide](https://www.fantasypros.com/2017/06/fantasy-football-game-changer-how-to-use-the-draft-wizard/)
- **Dynamic value:** Basketball Monster's DynV recomputes each player's value against the remaining pool, based on which stats have been removed. — [Basketball Monster](https://basketballmonster.com/drafttrackertutorials.aspx)
- **Auction dollar conversion (z-score / replacement):** $ = [(Budget − 1×roster spots)/roster spots] × (z above replacement / average z of above-replacement players) + 1. This makes an average draftable player cost the average budget per slot and a replacement player cost $1. The FanGraphs simplification for a typical league is 10.3 × (FVARz/3) + 1. — [FanGraphs Value Above Replacement Pt 3](https://fantasy.fangraphs.com/value-above-replacement-part-three/)
- Points-based version: every roster spot costs at least $1, and the remaining dollars are split among draftable players in proportion to their points over replacement (snippet). Replacement level is set by roster settings, for example the Nth player at a slot where N = teams × starters. — [Big Board valuation tip](https://www.getbigboard.com/harper-wallbanger/player-valuation-tip-1-playervalues2020); [FanGraphs community: replacing replacement value](https://community.fangraphs.com/replacing-replacement-value-in-fantasy-auctions/)
- **Inflation:** inflation = money left ÷ projected value left − 1. For example, $1,800 left against $1,500 of value is +20%, so the remaining players' prices go up (snippet from a 2026 auction guide). — [Athlon Sports 2026-27 auction guide](https://athlonsports.com/fantasy/fantasy-basketball-2026-27-auction-draft-guide); [RotoWire auction values](https://www.rotowire.com/basketball/auction-values.php)
- **H2H points strategy:** in points leagues, "your sole objective is raw fantasy point accumulation", games played or availability is the key trait, and high-usage players are favored. In Yahoo default scoring, efficiency is not penalized, which rewards high-volume shooters (snippets). — [Fantrax HQ points strategy](https://fantraxhq.com/fantasy-basketball-points-league-strategy-and-draft-guide-how-to-outsmart-your-league-mates/); [SportsEthos points guide 2026](https://sportsethos.com/top-posts/fantasy-basketball-draft-guide-2026-points-league-strategy/); [ESPN points strategy](https://www.espn.com/fantasy/basketball/story/_/id/20631092/fantasy-basketball-points-league-strategy)
- ESPN publishes H2H points draft *tiers by position*, a tiering format specific to points leagues. — [ESPN H2H points tiers 2023-24](https://www.espn.com/fantasy/basketball/story/_/id/38652674/2023-24-fantasy-basketball-head-head-points-draft-tiers-position)
- Hashtag supports "Standard / H2H / Minus 1" valuation modes and a GP penalty (10–30%) in its value calculations, but documents no formula. — [Hashtag Basketball](https://hashtagbasketball.com/fantasy-basketball-auction-values)

### Inferences
- Cheapest high-value addition for the user's H2H points tracker: availability % = 1 − Φ((nextPick − ADP)/σ), with σ = ADP/4 when real SD is missing. nextPick comes from the snake order the app already tracks.
- A better version would run about 1,000 simulations of the picks between now and the user's next turn. Each bot would pick from ADP plus noise, adjusted by its roster needs (the app already models lineup need).
- For points leagues, the recommendation score could be VORP, where replacement = the (teams × starters at that slot)-th player in projected fantasy points/game × projected GP, and ESPN position eligibility sets the slots. Weight VORP against the risk that the player is gone by the next pick, e.g. value lost by waiting = VORP(now) − E[best VORP available at next pick].
- Draft grades and projected standings can reuse the app's existing "live team rankings". A post-draft report could add steals and reaches (pick − ADP).

### Gaps
- No vendor publishes an exact recommendation algorithm. FantasyPros' simulation details are proprietary and described only in marketing copy, and nothing NBA-specific turned up.
- I found no documented dynamic auction inflation tracker for NBA besides Basketball Monster's DynV; its auction behavior is unconfirmed.
- I found no public NBA ADP source with standard deviations. FantasySP shows auction min/max/avg, which could yield SD through the range rule.
