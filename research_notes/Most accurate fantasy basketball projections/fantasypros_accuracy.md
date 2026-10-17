# FantasyPros NBA Expert Accuracy and Evidence on ECR Accuracy

Research date: 2026-09-29. Tools: WebSearch, WebFetch, direct curl probes of the Wayback Machine. The Wayback CDX API timed out or returned HTTP 504/429 on every attempt, so archive checks were done with per-URL "closest snapshot" probes (`https://web.archive.org/web/<year>/<url>`) instead. That method returns 302 when a capture exists and 404 when none exists.

## Does FantasyPros run NBA accuracy contests or leaderboards, and for which seasons?

### Takeaway
I found no evidence that FantasyPros has ever published an NBA (fantasy basketball) accuracy leaderboard. The live URL returns 404. The Wayback Machine has no captures at several candidate URLs from 2013 to 2025, while the matching NFL and MLB accuracy URLs are archived. FantasyPros' accuracy FAQ and methodology pages describe only football and baseball. Their NBA expert directory advertises "accuracy ratings" in boilerplate, but I found no actual NBA accuracy data behind it.

### Cited Findings
- `https://www.fantasypros.com/nba/accuracy/` returns HTTP 404 (fetched 2026-09-29). The NFL page `https://www.fantasypros.com/nfl/accuracy/` exists and is titled "2026 Fantasy Football Accuracy Scores" — [FantasyPros NFL accuracy](https://www.fantasypros.com/nfl/accuracy/) (search result title; the page body was not fetched).
- Wayback probes (curl, 2026-09-29):
  - `fantasypros.com/nba/accuracy/`, `/nba/accuracy.php` and `/nba/experts/accuracy.php` returned "404 NOT FOUND" (no capture) for 2013, 2017, 2021 and 2025.
  - `/nba/accuracy/index.php` returned 404 for 2013, 2017 and 2021.
  - `/nba/rankings/accuracy.php` returned 404 for 2021 and 2025.
  - Controls for the same method: `/nfl/accuracy/` resolved to a snapshot dated 20191231072656, `/mlb/accuracy/` to 20191231085030 and `/nba/` to 20191231064710. So the archive covers FantasyPros' NBA section and its other sports' accuracy pages, but not an NBA accuracy page at these URLs. Probes of `/nba/accuracy/draft.php`, `/nba/accuracy/weekly.php` and `/experts/nba/accuracy.php` returned nothing because of rate limiting, so those are untested. — [Wayback Machine](https://web.archive.org/web/2019/https://www.fantasypros.com/nfl/accuracy/)
- FantasyPros' accuracy FAQ says: "We rate the accuracy of each expert's cheat sheets (Preseason and In-Season) by comparing their player predictions to the actual outcomes." It also says: "We have In-Season accuracy scores going back to the 2009 season. Our Preseason accuracy scores go back to 2010." Every example on the page is football, and it gives no basketball methodology. — [FantasyPros FAQ /accuracy/](https://www.fantasypros.com/accuracy/)
- FantasyPros' support-center methodology articles found by search are titled "How do you measure the in-season accuracy of fantasy football experts?", "How do you measure the draft accuracy of fantasy football experts?" and "How do you measure the accuracy of fantasy baseball experts?". Search turned up no basketball equivalent. The support pages themselves returned 403 to WebFetch, so this rests on search titles only. — [support: baseball](https://support.fantasypros.com/hc/en-us/articles/115002308108-How-do-you-measure-the-accuracy-of-fantasy-baseball-experts); [support: football draft](https://support.fantasypros.com/hc/en-us/articles/115002307688-How-do-you-measure-the-draft-accuracy-of-fantasy-football-experts)
- The NBA experts directory is described in search snippets as featuring "rankings, accuracy ratings and advice from the industry's top fantasy basketball experts". When fetched, the page showed no accuracy ranks, scores or awards, only a directory of experts by outlet. — [FantasyPros NBA experts](https://www.fantasypros.com/experts/nba/)
- About 12 web searches with varied wording ("most accurate fantasy basketball expert FantasyPros", "fantasypros.com/nba/accuracy", expert-bio "#1" searches, and others) returned only football and baseball accuracy content, plus NBA rankings pages. None returned an NBA accuracy leaderboard, award announcement or expert bio citing an NBA FantasyPros accuracy award. — [FantasyPros accuracy articles hub](https://www.fantasypros.com/content/accuracy/) (seen as a search result; not fetched)

### Inferences
- The most likely explanation is that FantasyPros does not publish NBA accuracy scores, so there is no per-season NBA leaderboard for 2015–2026. This conclusion comes from converging absence of evidence, not from an explicit FantasyPros statement.
- The "accuracy ratings" wording on the NBA experts page looks like a template sentence reused from the NFL and MLB pages.

### Gaps
- I did not get a full Wayback CDX listing because the API timed out. An NBA accuracy page at a URL I didn't guess (for example under `/nba/accuracy/draft.php` or on a subdomain) can't be fully ruled out.
- I did not check the FantasyPros accuracy-articles hub (`/content/accuracy/`) article by article for NBA posts.
- I found no FantasyPros statement explicitly saying "we do not track NBA accuracy".

## Who were the top NBA experts each season, and do they persist?

### Takeaway
I could not answer this: I found no NBA accuracy results, so there are no names, scores or persistence figures to report. The closest parallel is baseball, where FantasyPros reports clear repeat winners.

### Cited Findings
- (Baseball, not NBA) In FantasyPros' 2025 fantasy baseball draft-rankings accuracy results, "41 experts qualify by submitting draft rankings for all positions in 2025". Ariel Cohen (FanGraphs) finished #1, followed by Joe Bond (Fantasy Six Pack) and Jody Smith (Draft Sharks). On persistence, the article says Cohen also won rankings accuracy in 2019 and has "dominated our projections accuracy contests" with five #1 finishes in seven years. Bond had his "fourth top-10 result in the last five years". — [FantasyPros, Feb 2026](https://www.fantasypros.com/2026/02/most-accurate-fantasy-baseball-rankings-experts-2025-results/)
- (Football, not NBA) FantasyPros runs a yearly football accuracy competition, with a 2025 draft accuracy winners announcement on X. DraftSharks promotes Jody Smith as the "Most Accurate Fantasy Football Expert 2026". — [FantasyPros on X](https://x.com/FantasyPros/status/2076751163589038299); [DraftSharks](https://www.draftsharks.com/kb/most-accurate-fantasy-football-experts) (search result titles only)

### Inferences
- Any claim that someone is the "most accurate NBA expert per FantasyPros" should be treated as unverified unless its source is produced.

### Gaps
- There are no NBA leaderboard names, scores or year-to-year persistence data.

## How does FantasyPros score accuracy, and is ECR scored and where does it place?

### Takeaway
FantasyPros has no NBA methodology to report. Football uses an "Accuracy Gap" in projected versus actual points. Baseball uses value-based rankings in standard 5x5, a player pool locked to an ECR cutoff, and cumulative error. The only FantasyPros ECR-versus-experts study I found is for 2010 football: consensus finished 2nd among 40+ experts.

### Cited Findings
- Football metric: "Accuracy Gap" is "the difference (absolute value) between an expert's projected points for a player and the actual points scored." — [FantasyPros FAQ](https://www.fantasypros.com/accuracy/)
- Baseball method, in four steps:
  1. Rank actual player performance by VBR (value-based ranking) in standard 5x5 categories.
  2. Lock the player pool using ECR cutoffs.
  3. Score each expert's rankings against the actual VBR results.
  4. Rank experts by cumulative error.

  — [FantasyPros 2025 MLB results](https://www.fantasypros.com/2026/02/most-accurate-fantasy-baseball-rankings-experts-2025-results/)
- The ECR study (fantasy football, 2010 season, published January 2011, tracking 40+ experts with FantasyPros' accuracy metric):
  - The "Consensus of All Experts" scored 60.5% and ranked 2nd overall. It "finished in the Top 10 for each of the 4 main positions... RB (#4), WR (#3), QB (#10), and TE (#9)."
  - A "2010 Top 5 Consensus" (the five most accurate 2010 experts combined) scored 61.6%, the best of anything tested.
  - FantasyPros' framing: "consolidated recommendations help to reduce the negative impact of outlier predictions."

  — [FantasyPros, "How Accurate are Expert Consensus Rankings?"](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)
- A FantasyPros FAQ snippet says "ECR™ is highly accurate – it finished in the Top 5 among all experts in 2010" (search snippet from the FAQ). — [FantasyPros FAQ/tools](https://www.fantasypros.com/tools/) (the snippet appeared in search results; the fetched page body did not contain it)
- FantasyPros also advertises "multi-year accuracy rankings – because when it comes to relying on industry leaders, consistency matters a lot" (football context). — [FantasyPros tools/FAQ](https://www.fantasypros.com/tools/)
- A July 2019 FantasyPros article, "Most Accurate Experts vs. Consensus Rankings", is a qualitative piece: 2018's most accurate football experts discuss where they differ from ECR. It gives no quantitative comparison of ECR with experts. — [FantasyPros, Jul 2019](https://www.fantasypros.com/2019/07/most-accurate-experts-vs-consensus-rankings-fantasy-football/)

### Inferences
- The 2010 "Top 5 Consensus" result has look-ahead bias: it picks the experts using the same season's accuracy. Only the "all experts" consensus (#2 of 40+) is a fair out-of-sample benchmark, and that is a single football season.
- In the user's 2021–26 backtest, the roto ECR beat their formula, ESPN projections, ESPN analysts and ADP. That is consistent in direction with FantasyPros' football finding that consensus lands near the top without always being #1. The only NBA evidence here is the user's own backtest.

### Gaps
- I found no study of ECR against individual experts for NBA.
- I found no multi-season FantasyPros statistic on where ECR ranks, even for NFL or MLB. The 2025 MLB article excerpt didn't say where ECR placed.

## Statements about consensus versus individual accuracy in NBA specifically

### Takeaway
I found none, either from FantasyPros or from third parties.

### Cited Findings
- The searches described above turned up no NBA-specific consensus-versus-expert statement. The only FantasyPros consensus-accuracy claims I found are for football (2010) — [FantasyPros 2011](https://www.fantasypros.com/2011/01/expert-consensus-rankings-accuracy/)

### Inferences
- In basketball, "ECR beats individual experts" is currently supported only by analogy to football (and to general wisdom-of-crowds reasoning) and by the user's own backtest.

### Gaps
- I did not search academic or other third-party NBA forecast-aggregation studies; that was out of scope for this note.

## Who contributes to the NBA ECR, and is there an ESPN-points ECR?

### Takeaway
The NBA ECR draws on many outlets, including Yahoo, CBS, RotoWire, Basketball Monster, Hashtag Basketball and FantasyPros staff. FantasyPros publishes a separate ESPN-points ECR page for 2026-27, with position variants and a rest-of-season version. I found no accuracy scoring for the points ECR.

### Cited Findings
- The NBA experts directory lists outlets including Yahoo! Sports, CBS Sports, Footballguys, FantasyPros (with a "Show 22 More" expansion for FantasyPros staff alone), Basketball Monster, RotoWire, RotoBaller and The Deep Shot, plus many independent analysts and podcasters. — [FantasyPros NBA experts](https://www.fantasypros.com/experts/nba/)
- Search snippets for the same page also list The Fantasy Authority, Hashtag Basketball, FB-Ninja, DraftKings, PredictionMachine, FantasyHub, theScore, numberFire and Legion Report (snippet only; the page's list changes over time). — [FantasyPros NBA experts](https://www.fantasypros.com/experts/nba/)
- FantasyPros' Draft Wizard for basketball is marketed as having "customizable rankings from 60+ fantasy basketball experts" (search snippet). — [Draft Wizard basketball](https://draftwizard.fantasypros.com/basketball/draft-software/)
- There are separate ECR pages for roto/categories (`overall.php`, titled "Roto / Categories") and ESPN points (`overall-points-espn.php`). There are also points-by-position pages (for example `c-points-espn.php`) and a rest-of-season points page (`ros-overall-points-espn.php`). The pages render client-side, so WebFetch could not see expert counts or lists. The roto page says "The publish date is provided for each expert." — [ESPN points ECR](https://www.fantasypros.com/nba/rankings/overall-points-espn.php); [Roto ECR](https://www.fantasypros.com/nba/rankings/overall.php); [ROS points](https://www.fantasypros.com/nba/rankings/ros-overall-points-espn.php)
- For fantasy football, FantasyPros says it gathers "consensus draft rankings from well over 100 experts across the three major scoring formats". This shows the practice of per-format ECR, but it is football, not NBA. — [FantasyPros tools/FAQ](https://www.fantasypros.com/tools/)

### Inferences
- The user used the roto ECR, not the ESPN-points ECR, to predict ESPN points. In their backtest this still beat the other sources. A natural next test is whether the points ECR (fewer contributors, probably) does better or worse than the roto ECR on ESPN points. I found no FantasyPros data on this.

### Gaps
- I don't know how many experts contribute to the points ECR compared with the roto ECR, or which ones; the pages are JavaScript-rendered.
- I don't know whether the points ECR is built from native points-league rankings or partly from roto rankings.
- I found no archived points-ECR history before 2026-27, and its first season is unknown.
