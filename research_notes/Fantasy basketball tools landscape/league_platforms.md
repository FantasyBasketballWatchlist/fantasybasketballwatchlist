# Fantasy Basketball League Platforms: Built-in Tools, Premium Tiers, Data Access

Research date: 2026-09-29. ~24 tool calls. Reddit was not searched directly; user sentiment comes from App Store pages and review aggregators, so it is thin. Several platform help pages (Fantrax premium features, Yahoo's old developer guide) redirected or returned empty pages; those gaps are noted.

## Q1: What each platform offers (tools, free vs premium, league formats)

### Takeaway
ESPN is free with basic in-app tools. Its recent additions (2024) are about convenience: a draft board, practice drafts using your league's settings, Quick Lineup, and mobile league-manager (LM) controls. It does not add analytics. Yahoo has put its analytics (lineup optimizer with win probability, trade hub, research assistant, advanced projections) behind Fantasy Plus/Ultra, and in 2025-26 made "High Score" (a simplified H2H points format co-branded with the NBA) the default for new leagues. Sleeper is testing new formats (Lock-In mode). Fantrax and CBS are the deep-customization and commissioner platforms, where dynasty/salary/contract features cost $100-150 per league-season.

### Cited Findings
**ESPN Fantasy Basketball**
- Features added for 2024-25 (article dated Sep 30, 2024): a "modernized draft board" showing every team's picks on one screen, color-coded by position (app only); personalized practice drafts against computer managers using your league's settings (app only); in-app LM controls for scoring settings, draft type/order, and draft date/time (previously desktop only); a "Quick lineup" button that fills lineup holes and benches players marked "O" based on injury status and schedule; lineup autosave in the app (previously desktop only). — [ESPN](https://www.espn.com/fantasy/basketball/story/_/id/41532734/2024-fantasy-basketball-draft-board-new-features-espn)
- That announcement says nothing about points-league-specific tools, projections, trade tools or waiver tools. — [ESPN](https://www.espn.com/fantasy/basketball/story/_/id/41532734/2024-fantasy-basketball-draft-board-new-features-espn)
- I found no ESPN announcement of new basketball game features for 2025-26. Searches returned only the 2024 article. — search results (see Gaps)
- ESPN publishes separate H2H points rankings/tiers and H2H category/roto rankings every season (e.g., 2025-26 and 2026-27 points-league rankings) and a cheat sheet with a schedule grid. — [ESPN points rankings 2025-26](https://www.espn.com/fantasy/basketball/story/_/id/46271067/fantasy-basketball-points-league-rankings-2025-26-nba-season); [ESPN points rankings 2026-27](https://www.espn.com/fantasy/basketball/story/_/id/49960162/fantasy-basketball-points-league-rankings-2026-27-nba-season); [ESPN points draft tiers](https://www.espn.com/fantasy/basketball/story/_/id/46449501/fantasy-basketball-points-league-draft-tiers-nba-2025-26); [ESPN cheat sheet/schedule grid](https://www.espn.com/fantasy/basketball/story/_/id/46539070/fantasy-basketball-cheat-sheet-2025-26-nba-player-rankings-schedule-grid)
- The ESPN Fantasy iOS app is rated 4.8/5 from about 2.1M ratings (all sports combined), is an Editors' Choice, and was at v9.11.1 as of late Sep 2026. It is free with in-app purchases (ESPN+). Praise centers on ESPN's integrated content and player blurbs. One long-time user complains that picking up a player sends you back to your team page instead of the waiver wire. — [App Store](https://apps.apple.com/us/app/espn-fantasy-sports-more/id555376968)
- Aggregated review complaints: crashes and "loading your roster" hangs, slow launch, no iPad multitasking, ads before use, removed widgets. Basketball-specific: position eligibility updates too slowly, and a player on IR can't be moved to an active slot until the next day. — [justuseapp review aggregate (2025)](https://justuseapp.com/en/app/555376968/espn-fantasy-sports-more/reviews)

**Yahoo Fantasy Basketball**
- Current tiers: Free ($0: public/private leagues, all scoring types, basic stats and matchups, "start active players"); **Plus $39.99/yr** (real-time draft recommendations, downloadable expert ranks, instant mock drafts, advanced stats and projections, lineup optimization, in-season analysis tools); **Ultra $79.99/yr** (everything in Plus, plus expert draft strategies, partner perks and fewer ads). For basketball, "Premium Depth Chart" and "Projected Min/Max" are not available. — [Yahoo Plus landing page](https://fantasysports.yahoo.com/lp/plus)
- Earlier or other pricing: $99.99 for "Fantasy Plus: All Sports," with promos of 60% off the first year and 28% off through Aug 23, 2025. **Conflict:** this does not match the $39.99/$79.99 tiers now on Yahoo's own page. Treat the landing page as current and the $99.99 figure as an earlier bundle. — [Yahoo search snippet/promo article](https://sports.yahoo.com/fantasy/article/get-28-off-yahoo-fantasy-plus--for-a-limited-time-only-125805504.html); [Yahoo Plus landing](https://fantasysports.yahoo.com/lp/plus)
- Named Plus tools: Assistant GM (lineup optimization with win-probability insights), Instant Mock Draft, Research Assistant (sit/start and add/drop comparisons), a Trade Hub showing every team's strengths and weaknesses with suggested trade partners, advanced stats on My Team and Players pages, "Start optimal players," and Draft Scout. — [Yahoo Plus benefits article](https://sports.yahoo.com/fantasy/article/the-yahoo-fantasy-plus-benefits-program-is-here-see-whats-inside-142137328.html); [Yahoo Draft Scout article](https://sports.yahoo.com/yahoo-fantasy-plus-now-with-draft-scout-and-more-new-features-184019271.html)
- **Yahoo Fantasy High Score** (with the NBA, an "official season-long fantasy game of the NBA"): 10-player rosters, 6 starters (2 guards, 3 frontcourt, 1 sixth man). Scoring is PTS 1, REB 1, AST 2, BLK 3, STL 3, with no turnovers. Only each starter's single best game of the week counts, so lineups are set once a week. It became the **default format for new Yahoo leagues in 2025-26** (article dated Oct 1, 2025). Classic H2H/roto formats are still available. — [Yahoo High Score 101](https://sports.yahoo.com/fantasy/article/high-score-101-yahoos-new-default-fantasy-basketball-format-has-arrived--heres-everything-to-know-160017444.html); [Yahoo Inc press release](https://www.yahooinc.com/press/yahoo-sports-and-nba-launch-new-simpler-season-long-fantasy-basketball-game-yahoo-fantasy-high-score); [NBA.com/playfantasy](https://www.nba.com/playfantasy)
- NBA.com's "play fantasy" page points to Yahoo High Score, and NBA.com publishes High Score rankings for 2026-27. So the NBA's "own" fantasy game is Yahoo-hosted, not a separate NBA platform. — [NBA.com playfantasy](https://www.nba.com/playfantasy); [NBA.com High Score top 150](https://www.nba.com/news/nba-fantasy-top-150-for-2026-27-high-score-leagues)

**Sleeper (NBA)**
- Sleeper's "Lock-In" mode for NBA: you draft normally, but each player counts for only **one game per week**, chosen by the manager. You must lock in a game before the player's next game tips off, and the player must be in your starting lineup that day. Once locked, the choice is irreversible and the lineup slot locks too. The format reduces the edge from players with more games in a week and rewards boom/bust players. — [RotoWire](https://www.rotowire.com/basketball/article/nba-fantasy-how-to-play-sleepers-new-lock-in-mode-75705) (article date not visible; see Gaps)

**Fantrax**
- Pitches itself as the most customizable platform. Free leagues are available in basketball and other sports. It is known for dynasty leagues and also supports keeper, redraft and best ball. — [Fantrax](https://www.fantrax.com/); [FantraxHQ commissioner article](https://fantraxhq.com/commissioners-corner-organizing-your-fantasy-league/)
- The Premium Commissioner league costs **$129.95 per league per season** (about $11 per manager in 12 teams). College basketball premium costs $99.95. Premium adds player salaries and salary caps, automated contracts, renewals/extensions, multi-season draft-pick trading and off-season trades. Fantrax Treasurer collects league fees for free. — [Fantrax premium (search snippet)](https://www.fantrax.com/newui/premiumLeague.go?gameId=600); [Fantrax premium features](https://www.fantrax.com/premium-league-features) (the page returned no content when fetched, so these details come from search snippets)

**CBS Sports**
- Basketball Commissioner costs **$149.99 per season** ($99.99 prepay promo, $129.99 early bird) and covers up to 30 teams. Commissioners can customize the draft, schedule, scoring and transactions. It includes chat and league news posts, keeper/dynasty support with history carried between seasons, and in-app commissioner tools. CBS also runs free and prize leagues. — [CBS Commissioner FAQ](https://www.cbssports.com/fantasy/basketball/games/commissioner/frequently-asked-questions); [CBS basketball games](https://www.cbssports.com/fantasy/games/basketball/)

### Inferences
- **ESPN H2H points players, strong points:** it is free; points leagues are a first-class format with dedicated rankings and tiers; Quick Lineup and autosave cut down on daily lineup chores; practice drafts use real league settings; the draft board is good. **Weak points (inferred, since no source shows these features):** I found no evidence that ESPN offers a basketball matchup win-probability tool, a trade analyzer or suggestions, a points-based streaming or games-remaining optimizer, or rest-of-season projections tuned to the league's custom points scoring. Users also report app reliability problems and slow position-eligibility updates. That opens room for third-party tools that pull an ESPN league and compute games-remaining × points-per-game projections, streaming picks and trade value using the league's own scoring weights.
- Yahoo's paywall (Assistant GM win probability, Trade Hub) sets the market price anchor at $40-80 a year for "in-platform analytics." ESPN users get none of this natively.
- Formats that count one game per week (Yahoo High Score's best-game rule, Sleeper Lock-In) undercut "games-per-week streaming" value. A tool built for ESPN H2H points should not assume every league values volume the same way.

### Gaps
- Could not confirm ESPN basketball features added for 2025-26 or 2026-27. No announcement surfaced. It is unknown whether ESPN added matchup projections or win probability for basketball, or any trade tools.
- Could not confirm Sleeper NBA's supported formats (points vs categories, dynasty/keeper) or when Sleeper launched NBA and Lock-In. The RotoWire article date wasn't visible.
- CBS and Fantrax in-season tools (projections, trade analyzers, lineup optimizers) were not documented in the sources I reached.
- Reddit was not searched. There are no systematic user-complaint data for Yahoo, Sleeper, Fantrax or CBS basketball.

## Q2: Data access for a third-party app to sync a user's league

### Takeaway
Sleeper is the easiest: a public, unauthenticated, read-only API whose NBA endpoints work even though the docs say NFL only. ESPN works through an unofficial API: public leagues need only the league ID, private leagues need the user's `espn_s2` and `SWID` cookies, and the host moved to `lm-api-reads.fantasy.espn.com`. Yahoo now requires **manual application approval** plus OAuth 2.0, and is **read-only**. Fantrax and CBS have unofficial or deprecated routes only.

### Cited Findings
**ESPN (unofficial v3)**
- The Python `espn-api` library (cwendt94) supports football, basketball, hockey and baseball, with about 981 stars and 53 open issues. Its integration tests hit live ESPN endpoints, so it breaks when ESPN changes things. — [GitHub cwendt94/espn-api](https://github.com/cwendt94/espn-api)
- Basketball objects include `League.free_agents(size, position)`, `box_scores()` (per-player points and breakdowns for home/away lineups), `scoreboard()`, team roster/wins/losses/standing, and player eligibleSlots, proTeam and acquisitionType. — [espn-api wiki Basketball Intro](https://github.com/cwendt94/espn-api/wiki/Basketball-Intro)
- Private leagues use `espn_s2` and `SWID` cookies (there is a known issue thread about obtaining these credentials). — [espn-api issue #549](https://github.com/cwendt94/espn-api/issues/549); [ESPN hidden API gist](https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b?permalink_comment_id=5186770)
- **Host change:** the working base is `https://lm-api-reads.fantasy.espn.com/apis/v3/games/{gameCode}/seasons/{season}/segments/0/leagues/{leagueId}`. The legacy `fantasy.espn.com` v3 host is unreliable and redirects to HTML unless browser headers are spoofed. The new host was live-tested in 2026. (I did not independently verify the basketball game code, commonly `fba`.) — [sleeperdynasty PR #4](https://github.com/calvinlmickens/sleeperdynasty/pull/4); [Lolindhir/fantasy-app issue #669](https://github.com/Lolindhir/fantasy-app/issues/669)
- ESPN offers no OAuth or official developer program. Cookie-based access means users must copy browser cookies by hand, and it breaks when the cookies expire.

**Yahoo (official, OAuth 2.0)**
- A Yahoo developer app alone is "no longer sufficient." Developers must apply for Fantasy API access through the Yahoo Sports Developer Portal and tie the approval to an existing client ID. Each application is reviewed by hand, and incomplete ones are closed without reply. Applications must describe the product, the data needed, the user base (estimated users over 3-6 months), and whether use is personal or single-league. — [Yahoo apply page](https://sports.yahoo.com/developer/access/); [Yahoo developer portal](https://sports.yahoo.com/developer)
- "The Yahoo Fantasy Sports API currently provides read access only. Write access is not available at this time" (exceptions can be requested). Yahoo may throttle excessive use. — [Yahoo apply page](https://sports.yahoo.com/developer/access/); [Yahoo developer portal](https://sports.yahoo.com/developer)
- The Python `yahoo-fantasy-api` library (v2.12.3, Apr 3, 2026) uses `yahoo_oauth` OAuth2 and covers leagues, teams, rosters, free agents, matchups and trades. `yfpy` is an alternative wrapper. — [PyPI yahoo-fantasy-api](https://pypi.org/project/yahoo-fantasy-api/); [yfpy](https://github.com/uberfastman/yfpy)

**Sleeper (public)**
- No token is needed, and the API is read-only. Keep calls under 1,000 per minute to avoid an IP block, and cache the roughly 5MB players endpoint no more than daily. Endpoints cover user, leagues by season, league, rosters, users, matchups, playoff brackets, transactions (waivers/FA/trades), traded picks, drafts and picks, players and trending adds/drops. The docs say "currently only NFL," and **commercial use requires licensing** by contacting Sleeper. — [Sleeper API docs](https://docs.sleeper.com/)
- **Verified by live test on 2026-09-29:** `GET https://api.sleeper.app/v1/state/nba` returned the 2026 preseason state (season start 2026-10-20). `/v1/players/nba/trending/add` returned data, and `/v1/players/nba` returned HTTP 200 (~2.5MB). So NBA works despite the NFL-only documentation. — direct API calls from this environment

**Fantrax (unofficial)**
- `fantraxapi` (meisnate12, PyPI v1.0.1) is an unofficial Python wrapper. Public leagues work by league ID. Private leagues need a login cookie captured through Selenium/Chrome. — [GitHub meisnate12/FantraxAPI](https://github.com/meisnate12/FantraxAPI); [PyPI fantraxapi](https://pypi.org/project/fantraxapi/0.2.2/); [docs](https://fantraxapi.kometa.wiki/)

**CBS (deprecated official)**
- The CBS v3 Fantasy API (`api.cbssports.com/fantasy`) is described as "deprecated but still available." It needs an access token, you must belong to a league to get one, and the CBS Development Center is reportedly offline. Available data includes rosters, transactions, live scoring, rules, schedule and playoff brackets. — [token fetcher GitHub](https://github.com/geoffharcourt/cbs_fantasy_sports_api_token_fetcher); [iron-tuna PR #252](https://github.com/krubins/iron-tuna/pull/252); [CBS dev docs](http://developer.cbssports.com/documentation/api/files/sports)

### Inferences
- Ease of league sync for a third-party app: Sleeper (no auth) > ESPN public leagues (league ID only) > ESPN private (cookie copy-paste) ≈ Fantrax private (cookie) > Yahoo (OAuth is user-friendly, but the app needs Yahoo's approval first) > CBS (deprecated).
- For an ESPN H2H points tool, hard-code the `lm-api-reads` host and build a clear cookie-entry flow with expiry handling. The unofficial API is the only option.
- A commercial product using Sleeper data needs a license from Sleeper. Personal or hobby use is fine under the docs.
- No platform offers public write access (add/drop, lineup set) for third parties, so tools can recommend moves but not make them.

### Gaps
- ESPN rate limits and cookie lifetime are undocumented.
- How long Yahoo's approval takes, and when the manual-approval policy started, is unknown (the page has no date).
- I did not verify whether the Fantrax or CBS routes still work in 2026.

## Q3: Recent (2023-2026) feature additions

### Takeaway
2024-2026 changes were mostly **format simplification** (Yahoo High Score as the 2025-26 default, Sleeper Lock-In), **monetization restructuring** (Yahoo Plus $39.99 / Ultra $79.99), **mobile parity** on ESPN (2024), and **tighter third-party access** (Yahoo manual approval and read-only; ESPN host migration).

### Cited Findings
- ESPN, Sep 2024: draft board, practice drafts using league settings, in-app LM controls, Quick Lineup, app autosave. — [ESPN](https://www.espn.com/fantasy/basketball/story/_/id/41532734/2024-fantasy-basketball-draft-board-new-features-espn)
- Yahoo, Oct 2025: High Score becomes the default format with the NBA. — [Yahoo](https://sports.yahoo.com/fantasy/article/high-score-101-yahoos-new-default-fantasy-basketball-format-has-arrived--heres-everything-to-know-160017444.html); [Yahoo Inc press](https://www.yahooinc.com/press/yahoo-sports-and-nba-launch-new-simpler-season-long-fantasy-basketball-game-yahoo-fantasy-high-score)
- Yahoo moves to Free/Plus/Ultra tiers; a 28%-off Plus promo ran through Aug 23, 2025. — [Yahoo Plus](https://fantasysports.yahoo.com/lp/plus); [Yahoo promo](https://sports.yahoo.com/fantasy/article/get-28-off-yahoo-fantasy-plus--for-a-limited-time-only-125805504.html)
- Sleeper launches Lock-In mode for NBA (date unconfirmed). — [RotoWire](https://www.rotowire.com/basketball/article/nba-fantasy-how-to-play-sleepers-new-lock-in-mode-75705)
- Yahoo API requires manual approval and is read-only (current as of 2026). — [Yahoo apply](https://sports.yahoo.com/developer/access/)
- ESPN API host moved to lm-api-reads (confirmed working 2026). — [sleeperdynasty PR #4](https://github.com/calvinlmickens/sleeperdynasty/pull/4)

### Inferences
- The industry trend toward "set once a week" formats is a response to daily-grind fatigue. ESPN has not followed as far as I found, so ESPN H2H points (daily lineups, volume-driven) is still where games-per-week and streaming tools matter most.

### Gaps
- No ESPN 2025 or 2026 basketball feature announcements found.
- No dated CBS, Fantrax or Sleeper basketball changelogs found.
- No reliable data on user counts or market share by platform.
