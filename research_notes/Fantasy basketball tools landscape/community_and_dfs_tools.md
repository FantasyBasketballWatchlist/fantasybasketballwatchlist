# Free/Community Fantasy Basketball Tools and DFS Tools

Research date: 2026-09-29. Star counts are as fetched on this date. Reddit could not be reached: old.reddit.com fetch was blocked, and site:reddit.com web searches returned no Reddit posts. As a result, no r/fantasybball "I built a tool" posts are cited, and popularity claims rest on GitHub stars rather than community discussion.

## Which community tools are popular and what gap do they fill that paid sites don't?

### Takeaway
The most-starred community projects are libraries that connect to leagues (espn-api at about 981 stars, yfpy at about 268, yahoo_fantasy_api at about 110) and DFS optimizers (pydfs-lineup-optimizer at about 449). Apps built for end users are mostly small (0-34 stars), often abandoned, and tied to one platform. They fill one gap: analysis of *your own league* (H2H category matchup projections, league-wide category comparisons, chat bots). Content sites like Hashtag Basketball cover general tools such as schedule grids, trade analyzers and punt rankings, and they are cheap ($2.50/month premium).

### Cited Findings
**Libraries that connect to leagues**
- cwendt94/espn-api: 981 stars, 293 forks, MIT license, 837 commits, 53 open issues. It supports fantasy football and basketball, with "NHL, MLB, and WNBA ... in development". It uses modern tooling (uv, type checking) and has a debug mode that prints requests and responses — [GitHub](https://github.com/cwendt94/espn-api)
- espn-api includes basketball-specific Box Score / Box Player classes, free agents, matchup periods and full schedule access — [espn-api wiki](https://github.com/cwendt94/espn-api/wiki)
- uberfastman/yfpy: Yahoo Fantasy API wrapper, 268 stars, **GPL-3.0**. Supports NFL, NHL, MLB and NBA. Needs Python 3.10+ and is tested through 3.13. Ships Docker support and a test suite — [GitHub](https://github.com/uberfastman/yfpy)
- spilchen/yahoo_fantasy_api: 110 stars, 37 forks, MIT. Covers game, league, team and player navigation, plus stat categories, weekly schedules and free agents. The README examples are MLB — [GitHub](https://github.com/spilchen/yahoo_fantasy_api)

**Community apps and analyzers (GitHub)**
- The most-starred repo on the fantasy-basketball GitHub topic is KengoA/fantasy-basketball (268 stars, Jupyter). It does scraping and NN/boosting predictions of player performance and was last updated July 2023. Also listed: jdguggs10/flaim (22 stars, a TypeScript "Fantasy Sports MCP Platform", updated Sep 2026), elwan9880/Yahoo_fantasy_basketball_analyzer (16 stars, last updated Oct 2021) and KengoA/fantasy-ga (6 stars, a genetic algorithm for DraftKings lineups, Oct 2024). The topic lists 48+ repos, including Court Vision (tracks trending players) and waiver-wizard — [GitHub topic](https://github.com/topics/fantasy-basketball)
- wcrasta/ESPN-Fantasy-Basketball: 34 stars, MIT, **no longer maintained as of Apr 22, 2023**. It computed stats for ESPN H2H Most Categories leagues by scraping with ChromeDriver — [GitHub](https://github.com/wcrasta/ESPN-Fantasy-Basketball)
- ahy3nz/catsketball: a Streamlit ESPN analyzer (MIT, 1 star, 221 commits). It does league-wide comparisons, roto-style scoring and H2H matchups over custom date ranges, and needs ESPN cookies — [GitHub](https://github.com/ahy3nz/catsketball)
- giasemidis/espn-nba-fantasy: 8 stars, 7 forks. It does H2H weekly projections using a Monte Carlo matchup simulation, plus post-round analysis of each team against the whole league — [GitHub](https://github.com/giasemidis/espn-nba-fantasy)
- martincham/espn-nba-fantasy-analyzer produces overall and per-category player valuations over different timespans. lucifer0096/NBA-Analytics is a pipeline that runs collector → leak-free features → LightGBM projections → PuLP optimizer → Streamlit, on ESPN's public APIs "no auth, no API key", with daily GitHub Actions runs — [search result summary](https://github.com/lucifer0096/NBA-Analytics); [martincham](https://github.com/martincham/espn-nba-fantasy-analyzer)
- A Google Workspace Marketplace add-on called "Algo Fantasy Basketball" exists for Sheets. I did not open its details — [Workspace Marketplace](https://workspace.google.com/marketplace/app/algo_fantasy_basketball/114553856405)

**Discord bots**
- famendola1/fantasy-discord-bot (Go, Yahoo fantasy basketball only). DMcP89/Harambot (Python, Yahoo). LeGitJames/fishBallersDiscord (Yahoo; league history and draft lottery tracking). coolbrett's "FBBot" (pycord + Firebase, ESPN H2H points basketball) — [search summary](https://github.com/famendola1/fantasy-discord-bot); [fishBallers](https://github.com/LeGitJames/fishBallersDiscord)
- dtcarls/fantasy_football_chat_bot (307 stars, GPL-3.0) posts scoreboards, power rankings, trophies and waiver reports to GroupMe, Discord and Slack via Docker. It is **football only**, so there is no mature basketball equivalent at that level — [GitHub](https://github.com/dtcarls/fantasy_football_chat_bot)

**Free and cheap web tools / stats sites**
- Hashtag Basketball offers about 24 free tools: projections (top 30), rankings, dynasty and points rankings, Advanced NBA Schedule Grid, streaming grid, playoff schedule, trade analyzer, injury database, playing-time trends and defense matchups. Premium is **$2.50/month** (Patreon) and adds full projections, mock drafts, a premium schedule grid, waiver rankings, a matchup planner, trade and waiver "machines" and league scouting reports — [Hashtag Basketball](https://hashtagbasketball.com/)
- Cleaning the Glass stats cost $5/month or $50/year — [CTG via search](https://cleaningtheglass.com/introducing-insider/)
- PBP Stats is free, with a $2/month membership (Patreon). Its open-source `pbpstats` Python package parses stats.nba.com and data.nba.com play-by-play into "enhanced PBP" — [Patreon](https://www.patreon.com/pbpstats); [pbpstats docs](https://pbpstats.readthedocs.io/)
- Basketball-Reference sits behind Cloudflare and reportedly rate-limits at about 20 requests/minute (429 page). Its terms restrict automated access — [Sports-Reference 429](https://www.sports-reference.com/429.html); [NBAAnalytic](https://nbaanalytic.com/articles/free-basketball-data-sources-ranked.html). (The ~20/min figure comes from a search summary, not the primary page.)

**DFS (brief)**
- DailyFantasyFuel: free projections and free optimizer, aimed at beginners and cash games — [Stokastic best DFS tools](https://www.stokastic.com/articles/dfs-strategy/best-dfs-tools). (Its /nba/optimizer URL returned 404 on this date, so the current URL is unverified.)
- SaberSim runs play-by-play game simulations that feed its lineup builder, aimed at tournaments. Starter is $97/month (500 lineups), Pro $197, Ultimate $297, with a $7/7-day trial — [SaberSim pricing](https://www.sabersim.com/pricing); [Stokastic comparison](https://www.stokastic.com/articles/nfl-dfs/stokastic-sims-vs-sabersim-vs-rotogrinders-nfl-2026)
- Stokastic uses contest simulation that ranks lineups by simulated ROI, with ownership projections. Core All-Access is $199.95/month and MAX is $399.95/month, with a free entry point to Sims — [Stokastic comparison](https://www.stokastic.com/articles/nfl-dfs/stokastic-sims-vs-sabersim-vs-rotogrinders-nfl-2026) (Stokastic is a vendor comparing itself to competitors, so treat its framing as biased)
- FantasyPros offers DFS cheat sheets and an optimizer — [search summary](https://alternativeto.net/software/daily-fantasy-fuel)
- Open source: DimaKudosh/pydfs-lineup-optimizer has 449 stars, **MIT**, 167 forks and 155 open issues. It covers DraftKings, FanDuel, Yahoo, FantasyDraft and more across 15+ sports including NBA, with CSV import, multiple lineups, stacking, exposure limits and randomness — [GitHub](https://github.com/DimaKudosh/pydfs-lineup-optimizer)

### Inferences
- Community tools fill the gap of personalised analysis of your own league. They pull your league's rosters and schedule and simulate your actual H2H categories matchup. Paid sites mostly sell projections and generic tools. Hashtag's premium "matchup planner" and "league scouting" are the closest paid equivalent.
- Community apps are fragile. Many are single-author, low-star and abandoned (wcrasta 2023, elwan9880 2021). The libraries (espn-api, yfpy) are what last.
- The basketball chat-bot space is thin compared with football's dtcarls bot.

### Gaps
- No r/fantasybball posts could be retrieved (Reddit blocked), so I could not check which apps Reddit users actually favour (for example the community trade/punt calculators).
- I did not verify last-commit dates for espn-api, yfpy or yahoo_fantasy_api. The fetches did not show them.
- I did not research FantasyLabs or RotoGrinders pricing and features in detail, beyond RotoGrinders appearing in the Stokastic comparison title.
- No Streamlit community gallery entries were found specifically for fantasy basketball.

## How do they connect to leagues (ESPN cookies, Yahoo OAuth, Sleeper API)? Any gotchas?

### Takeaway
ESPN private leagues need the `espn_s2` and `SWID` browser cookies, which expire. Yahoo needs a registered developer app (consumer key and secret) plus a three-legged OAuth2 flow with tokens stored in a file. Sleeper's public API is read-only and needs no auth, but its official docs still say "only NFL" even though Sleeper hosts NBA leagues.

### Cited Findings
- ESPN: `League(league_id, year, espn_s2='...', swid='{...}')`. SWID is written with braces (`{XXXXXXXX-...}`). Instructions for finding the cookies are in GitHub discussion #150. Cookies expire and have to be refreshed. The year must be given explicitly. Logging in is recommended even for public leagues so that recent activity is available — [espn-api wiki](https://github.com/cwendt94/espn-api/wiki)
- Community ESPN apps (catsketball, giasemidis) ask users to paste their browser cookies (SWID/ESPN_S2) — [catsketball](https://github.com/ahy3nz/catsketball); [giasemidis](https://github.com/giasemidis/espn-nba-fantasy)
- Yahoo (yahoo_fantasy_api) uses `yahoo_oauth` with a consumer key and secret and an `oauth2.json` file. Tokens are checked and refreshed — [GitHub](https://github.com/spilchen/yahoo_fantasy_api)
- Yahoo (yfpy): on first use it runs a browser-based three-legged OAuth2 handshake. It supports `.env` files, passing tokens as `yahoo_access_token_json`, and persistent tokens with auto-refresh. Gotcha: Yahoo API calls sometimes fail with cryptic errors, and re-running usually fixes them — [GitHub](https://github.com/uberfastman/yfpy)
- Sleeper: "read-only HTTP API that is free to use for non-commercial purposes". No token is needed. Keep calls under 1,000/minute or the IP gets blocked. Call the player dump (~5MB) at most once a day. Endpoints take a `<sport>` path parameter, but the docs say "Currently only NFL is supported" — [Sleeper docs](https://docs.sleeper.com/); Sleeper does run NBA redraft, keeper and dynasty leagues — [Sleeper](https://sleeper.com/fantasy-basketball)
- Some community tools get data by scraping instead of using APIs (wcrasta used ChromeDriver). That approach tends to break — [GitHub](https://github.com/wcrasta/ESPN-Fantasy-Basketball)

### Inferences
- For a user-facing web app, ESPN cookie paste is the path with the least friction but the worst security and UX. Users hand over session cookies, and those expire. Yahoo OAuth needs registering a Yahoo developer app, and a hosted service would need a redirect URI.
- Licensing matters if you depend on a library. yfpy is GPL-3.0, which is copyleft. yahoo_fantasy_api and espn-api are MIT.

### Gaps
- I could not confirm whether `api.sleeper.app/v1/.../nba/...` endpoints actually return NBA league data. The docs and the product disagree, so it needs a live test.
- I did not find the current cookie lifetime for ESPN, or any recent (2025-26) ESPN API breaking changes.

## Open-source code worth learning from (lineup optimizer, matchup win-probability sim, schedule grids) and licenses

### Takeaway
The most useful references are giasemidis/espn-nba-fantasy for H2H category Monte Carlo simulation, pydfs-lineup-optimizer (MIT) for ILP lineup construction, lucifer0096/NBA-Analytics for an end-to-end projection → PuLP → Streamlit pipeline, and the espn-api basketball box-score and schedule classes for weekly games-per-team logic.

### Cited Findings
- giasemidis runs 100,000 simulations of a matchup. It samples counting stats from **Poisson** distributions around player means and percentage stats from **Gaussian** distributions with SD = 0.2× mean, following each player's schedule for the week. Injured players are excluded and day-to-day players are counted as available. The output is a win probability per category — [GitHub](https://github.com/giasemidis/espn-nba-fantasy) (license not shown in the fetch)
- pydfs-lineup-optimizer (MIT) handles multi-lineup optimisation with stacking, exposure caps, randomness and site rule compliance, with NBA examples from Yahoo CSVs — [GitHub](https://github.com/DimaKudosh/pydfs-lineup-optimizer)
- KengoA/fantasy-ga uses a genetic algorithm for DraftKings lineups (Oct 2024) — [GitHub topic](https://github.com/topics/fantasy-basketball)
- lucifer0096/NBA-Analytics: LightGBM projections with leak-free features, a PuLP optimizer, a Streamlit dashboard and daily GitHub Actions — [GitHub](https://github.com/lucifer0096/NBA-Analytics)
- espn-api exposes matchup periods and the full schedule, which is the raw material for a schedule or streaming grid — [wiki](https://github.com/cwendt94/espn-api/wiki)
- The pbpstats package (open source) gives possession-level play-by-play — [docs](https://pbpstats.readthedocs.io/)

### Inferences
- The Poisson/Gaussian simulation is a simple, easy-to-copy baseline but has known weaknesses. Poisson under-disperses high-variance stats like 3PM and blocks. Modelling FG% with a Gaussian ignores attempts-weighting. Better would be to simulate makes and attempts and then compute the percentage. It also treats stats as independent, but points, FGA and turnovers are correlated.
- MIT code (espn-api, pydfs, wcrasta, catsketball) can be reused freely with attribution. GPL-3.0 code (yfpy, dtcarls) forces derivative distributions to be GPL too.

### Gaps
- I did not verify licenses for giasemidis, NBA-Analytics, KengoA or martincham.
- I found no dedicated open-source "schedule grid / streaming optimizer" repo for NBA fantasy. Hashtag's grid is closed-source.
