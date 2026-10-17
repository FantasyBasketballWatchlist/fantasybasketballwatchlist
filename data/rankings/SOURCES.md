# Preseason fantasy basketball rankings (historical snapshots)

Every row in these CSVs was parsed programmatically from an archived page (Wayback Machine raw `id_` capture). Nothing was hand-typed.
Snapshot timestamps are Wayback UTC capture times; each is strictly before that season's opening night.

Openers: 2021-22: 2021-10-19, 2023-24: 2023-10-24, 2024-25: 2024-10-22, 2025-26: 2025-10-21

Names are kept exactly as published (e.g. FantasyPros uses "Russell Westbrook III", "Michael Porter Jr."); team/position suffixes are stripped into a separate `team` column where available.

ADP files: `rank` is the order by that ADP column (ties broken by the page's own order); players with no value in that column are dropped. `fp_adp_avg` also keeps the per-site columns.

## espn_points_2021-22.csv

- Snapshot URL: http://web.archive.org/web/20210826141459/https://www.espn.com/fantasy/basketball/story/_/id/30662416
- Snapshot timestamp: 20210826141459 (2021-08-26)
- Players: 200
- Top 5: Nikola Jokic, Giannis Antetokounmpo, Luka Doncic, James Harden, Kevin Durant
- Notes: Article "Updated fantasy basketball head-to-head points rankings" (Snellings); in-page "Latest update: August 11" (2021). Only pre-opener capture of this article in Aug-Oct 2021; next capture (20211020034151) is after the opener.

## espn_points_2023-24.csv

- Snapshot URL: http://web.archive.org/web/20231023033136/https://www.espn.com/fantasy/basketball/story/_/id/37906560/fantasy-nba-rankings-2023-24-head-head-points-h2h
- Snapshot timestamp: 20231023033136 (2023-10-23)
- Players: 200
- Top 5: Nikola Jokic, Giannis Antetokounmpo, Jayson Tatum, Luka Doncic, Joel Embiid
- Notes: Latest pre-opener capture (earlier 20230929 capture had only 150 players).

## espn_points_2024-25.csv

- Snapshot URL: http://web.archive.org/web/20241007013101/https://www.espn.com/fantasy/basketball/story/_/id/41287422/fantasy-basketball-points-league-rankings-2024-25-nba-season
- Snapshot timestamp: 20241007013101 (2024-10-07)
- Players: 150
- Top 5: Nikola Jokic, Luka Doncic, Shai Gilgeous-Alexander, Victor Wembanyama, Giannis Antetokounmpo
- Notes: In-page "Updated: Oct. 1". Latest pre-opener capture.

## espn_points_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20251016013415/https://www.espn.com/fantasy/basketball/story/_/id/46271067/fantasy-basketball-points-league-rankings-2025-26-nba-season
- Snapshot timestamp: 20251016013415 (2025-10-16)
- Players: 150
- Top 5: Nikola Jokic, Shai Gilgeous-Alexander, Giannis Antetokounmpo, Victor Wembanyama, Luka Doncic
- Notes: Latest pre-opener capture.

## fantrax_points_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20250922134532/https://fantraxhq.com/jacob-dunnes-2025-fantasy-basketball-points-league-top-250-rankings/
- Snapshot timestamp: 20250922134532 (2025-09-22)
- Players: 250
- Top 5: Nikola Jokic, Victor Wembanyama, Shai Gilgeous-Alexander, Giannis Antetokounmpo, Luka Doncic
- Notes: Jacob Dunne top-250 points rankings, published 2025-09-20, modified 2025-09-22. Scoring stated in article: PTS 1, REB 1.2, AST 1.5, BLK 3, STL 3, TO -1 (NOT ESPN default).

## fp_adp_avg_2023-24.csv

- Snapshot URL: http://web.archive.org/web/20231017101417/https://www.fantasypros.com/nba/adp/overall.php
- Snapshot timestamp: 20231017101417 (2023-10-17)
- Players: 253
- Top 5: Nikola Jokic, Luka Doncic, Giannis Antetokounmpo, Joel Embiid, Jayson Tatum
- Notes: ADP column "AVG" of FantasyPros ADP table (page columns: Yahoo, ESPN, CBS, AVG); ranked by that column, players with no value in it dropped.

## fp_adp_avg_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20251005043523/https://www.fantasypros.com/nba/adp/overall.php
- Snapshot timestamp: 20251005043523 (2025-10-05)
- Players: 273
- Top 5: Nikola Jokic, Victor Wembanyama, Shai Gilgeous-Alexander, Giannis Antetokounmpo, Luka Doncic
- Notes: ADP column "AVG" of FantasyPros ADP table (page columns: Yahoo, ESPN, AVG); ranked by that column, players with no value in it dropped.

## fp_adp_espn_2023-24.csv

- Snapshot URL: http://web.archive.org/web/20231017101417/https://www.fantasypros.com/nba/adp/overall.php
- Snapshot timestamp: 20231017101417 (2023-10-17)
- Players: 193
- Top 5: Nikola Jokic, Giannis Antetokounmpo, Luka Doncic, Jayson Tatum, Joel Embiid
- Notes: ADP column "ESPN" of FantasyPros ADP table (page columns: Yahoo, ESPN, CBS, AVG); ranked by that column, players with no value in it dropped.

## fp_adp_espn_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20251005043523/https://www.fantasypros.com/nba/adp/overall.php
- Snapshot timestamp: 20251005043523 (2025-10-05)
- Players: 199
- Top 5: Nikola Jokic, Shai Gilgeous-Alexander, Victor Wembanyama, Giannis Antetokounmpo, Luka Doncic
- Notes: ADP column "ESPN" of FantasyPros ADP table (page columns: Yahoo, ESPN, AVG); ranked by that column, players with no value in it dropped.

## fp_adp_yahoo_2023-24.csv

- Snapshot URL: http://web.archive.org/web/20231017101417/https://www.fantasypros.com/nba/adp/overall.php
- Snapshot timestamp: 20231017101417 (2023-10-17)
- Players: 209
- Top 5: Nikola Jokic, Luka Doncic, Joel Embiid, Jayson Tatum, Shai Gilgeous-Alexander
- Notes: ADP column "Yahoo" of FantasyPros ADP table (page columns: Yahoo, ESPN, CBS, AVG); ranked by that column, players with no value in it dropped.

## fp_adp_yahoo_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20251005043523/https://www.fantasypros.com/nba/adp/overall.php
- Snapshot timestamp: 20251005043523 (2025-10-05)
- Players: 255
- Top 5: Nikola Jokic, Victor Wembanyama, Giannis Antetokounmpo, Shai Gilgeous-Alexander, Luka Doncic
- Notes: ADP column "Yahoo" of FantasyPros ADP table (page columns: Yahoo, ESPN, AVG); ranked by that column, players with no value in it dropped.

## fp_ecr_2021-22.csv

- Snapshot URL: http://web.archive.org/web/20211018042137/https://www.fantasypros.com/nba/rankings/overall.php
- Snapshot timestamp: 20211018042137 (2021-10-18)
- Players: 341
- Top 5: Nikola Jokic, Stephen Curry, James Harden, Luka Doncic, Karl-Anthony Towns
- Notes: Page heading "Fantasy Basketball Draft Rankings (2021-22)" (default = roto/category scoring). Parsed from HTML table.

## fp_ecr_2023-24.csv

- Snapshot URL: http://web.archive.org/web/20230925210141/https://www.fantasypros.com/nba/rankings/overall.php
- Snapshot timestamp: 20230925210141 (2023-09-25)
- Players: 551
- Top 5: Nikola Jokic, Joel Embiid, Jayson Tatum, Tyrese Haliburton, Luka Doncic
- Notes: Page heading "Fantasy Basketball Draft Rankings (2023-24)" (default = roto/category scoring). Parsed from HTML table.

## fp_ecr_2024-25.csv

- Snapshot URL: http://web.archive.org/web/20241008221318/https://www.fantasypros.com/nba/rankings/overall.php?partner=nbadotcom
- Snapshot timestamp: 20241008221318 (2024-10-08)
- Players: 329
- Top 5: Nikola Jokic, Victor Wembanyama, Luka Doncic, Shai Gilgeous-Alexander, Joel Embiid
- Notes: No capture of the plain overall.php URL in Aug-Oct 2024; this is the nba.com-partner variant of the same page. Embedded ecrData: type=Draft, scoring=ROTO, experts=8, last_updated=10/08.

## fp_ecr_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20251019185648/https://www.fantasypros.com/nba/rankings/overall.php
- Snapshot timestamp: 20251019185648 (2025-10-19)
- Players: 373
- Top 5: Nikola Jokic, Victor Wembanyama, Shai Gilgeous-Alexander, Luka Doncic, Giannis Antetokounmpo
- Notes: Embedded ecrData: type=Draft, scoring=ROTO, experts=8, last_updated=10/18.

## fp_points_espn_2025-26.csv

- Snapshot URL: http://web.archive.org/web/20251019185601/https://www.fantasypros.com/nba/rankings/overall-points-espn.php
- Snapshot timestamp: 20251019185601 (2025-10-19)
- Players: 396
- Top 5: Nikola Jokic, Victor Wembanyama, Giannis Antetokounmpo, Luka Doncic, Shai Gilgeous-Alexander
- Notes: Embedded ecrData: type=Draft - Points, scoring=ESPN, experts=7, last_updated=10/18.

## Not available (skipped)

- espn_points 2021-22 later snapshot: the Oct 2021 update (in-page "Latest update: Oct. 19") was only captured at 20211020034151, after the opener, so the Aug 26 capture of the Aug 11 list is used instead.
- fp_points_espn 2021-22, 2023-24, 2024-25: no Wayback capture of overall-points-espn.php between Aug 1 and the opener (captures exist 20211025, 20221018, 20231129, 20241203 - all after openers or wrong season).
- fp_adp_* 2021-22: capture 20210914135750 shows "Sorry, this report is not available"; capture 20210803050204 is stale 2020-21 ADP (no 2021 rookies such as Cade Cunningham). 20211026 capture is post-opener.
- fp_adp_* 2024-25: only pre-opener capture (20240803013922) is stale 2023-24 ADP (no 2024 rookies such as Zaccharie Risacher/Alex Sarr/Reed Sheppard).
- fp_adp_cbs: CBS column exists in 2023-24 ADP but was not requested; it is retained inside fp_adp_avg_2023-24.csv as adp_cbs.
- fantrax_points 2021-22, 2023-24, 2024-25: no preseason capture of a FantraxHQ points-league rankings article (2024-25 top-200 URL has no capture before the opener; the 2023 points article is first captured 2023-12-05).

## 2026-27 (prospective; captured live on 2026-09-29, before the Oct 20, 2026 opener)

| File | Players | Source | Page data |
|---|---|---|---|
| fp_ecr_2026-27.csv | 311 | https://www.fantasypros.com/nba/rankings/overall.php | ROTO, 6 experts, last updated 9/28 |
| fp_points_espn_2026-27.csv | 308 | https://www.fantasypros.com/nba/rankings/overall-points-espn.php | ESPN points, 5 experts, last updated 9/28 |
| fp_adp_avg_2026-27.csv | see file | https://www.fantasypros.com/nba/adp/overall.php | Yahoo + ESPN ADP average |

ESPN's 2026-27 points-league rankings article (story id 49960162) returned an empty response on this date and was not saved.
These lists keep changing until opening night; re-capture closer to Oct 20 for a same-date comparison with ESPN and BPV.
