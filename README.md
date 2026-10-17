# Hoopothesis

Live at https://hoopothesis.cc

Player values for ESPN points leagues, built on **BPV (Basketball Performance Value)**: expected fantasy points per team game from rostering a player, counting his production, how often he plays, and the free agent you can stream when he's out long-term.

- **Rankings** (`/`): search any player for their BPV breakdown, an 80% likely range, and fantasy-playoff game count, plus the top-25 rankings. Between seasons, players are shown on next season's team.
- **Draft** (`/draft`): a snake-draft tracker with suggested picks, team rankings and position outlook. Pick your draft slot at the top of the clock card.
- **League** (`/league`): up to 20 teams; each team's players with BPV, and teams ranked by the BPV of their best starting lineup.
- **Trade Analyzer** (`/trade-analyzer`): compares both sides by value over replacement, so 2-for-1 deals account for the roster spot.
- **Waiver Wires** (`/waiver-wires`): recent risers and fallers, split into minutes changes (which tend to last) and hot or cold shooting (which tends to fade).

The method, and the backtests behind every constant, are written up in [docs/BPV-methodology.md](docs/BPV-methodology.md).

## Run it

```
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:8080. On Windows you can double-click `runthis.bat`.

Before each season, BPV blends in ESPN's public preseason projections (per game and projected games), which beat both BPV and ESPN alone in testing. During the season the site also reads the NBA's official injury report (every 15 minutes on game days) to show each player's status, chance of playing and this week's expected points, and to estimate how much of the rest of the season an injured player will miss. That needs Java and `pip install -r requirements-extra.txt` (which also installs the analysis-script packages); without them everything else still works.

The first load downloads season game logs from stats.nba.com, which takes a few seconds. They're cached in `data/cache/`: completed seasons permanently, the current season for 6 hours.

Settings (environment variables):

| Variable | Default | Purpose |
|---|---|---|
| `NBA_SEASON` | automatic (switches in October) | force a season, e.g. `2025-26` |
| `PORT` / `HOST` | `8080` / `127.0.0.1` | where the app listens |
| `FLASK_DEBUG` | off | set to `1` for the auto-reloader and debugger. Local only: the debugger can run code. |
| `NBA_CACHE_TTL_SECONDS` | `21600` | how often the current season is refreshed |
| `LEAGUE_TEAMS` / `LEAGUE_ROSTER_SIZE` | `10` / `13` | your league's size; sets the replacement level (teams × roster size) |

## Scoring BPV against other rankings

Before the season starts (the 2026-27 season opens October 20, 2026), open the app at least once (it saves the preseason projection to `data/preseason/`, which BPV uses as the early-season starting point) and run `python -m analysis.snapshot` and save other sites' rankings the same week as CSV files with a `name` column in `data/snapshots/`. Commit them, so the dates prove they were made before the season. The app also saves snapshots itself whenever it runs: the latest preseason ranking for each season (`bpv_<date>_pre_<season>.csv`, replaced until opening night) and one a week during the season (`bpv_<date>_auto.csv`). It rescores them automatically; `python -m analysis.accuracy_tracker` does the same by hand. After the season, run with `BACKTEST_LAST_SEASON` set to that season's start year, e.g. `python -m analysis.draft_sim --season 2026-27 --ranking BPV=data/snapshots/bpv_<date>.csv --ranking ESPN=data/snapshots/espn_<date>.csv`.

## Manual inputs

`data/overrides.json` holds what the stats can't know:

```json
{
  "injuries": {
    "Player Name": {"out_for_season": true},
    "Another Player": {"out_games": 10}
  },
  "role_changes": {
    "Player Name": {"since": "2026-01-15"}
  }
}
```

A known injury also affects teammates: in season they get a production boost; between seasons the injured player's minutes stop counting as roster competition. Names are matched ignoring accents, case and periods. Keys starting with `_` are ignored (the file ships with examples).

## Code layout

| File | What it does |
|---|---|
| `nba_data.py` | stats.nba.com access: whole-season game logs and draft history, with a disk cache |
| `bpv.py` | ESPN scoring, availability and absence patterns, shrinkage, replacement level, rookie baselines |
| `ratings.py` | computes every player's BPV using the backtested constants |
| `app.py` | Flask routes and JSON API (`/api/players`, `/api/player`, `/api/rankings`, `/api/trade`, `/api/waiver`, `/api/meta`) |
| `analysis/backtest.py` | chooses the constants; writes `analysis/results.json` |
| `analysis/draft_sim.py` | simulated drafts to compare ranking lists (yours, ESPN, ADP...) |
| `analysis/robustness.py` | confidence intervals, per-season checks, comparison tuned only on earlier seasons; writes `analysis/robustness.json` |
| `analysis/preseason_production.py` | between-season projection tests; source of the age curve |
| `analysis/decay_test.py` | exponential decay vs the last-5 rule |
| `analysis/snapshot.py` | saves today's rankings to `data/snapshots/` so they can be scored after the season |
| `analysis/collect.py` | daily data collection without the app: fresh data, BPV and ESPN snapshots, scoring; meant to be run on a schedule by the website's host once it's published; status in `data/collect_status.json` |
| `analysis/accuracy_tracker.py` | scores every saved snapshot against the games played since (error vs a simple benchmark, ranking, range coverage); runs automatically from the home page every 6 hours |
| `analysis/test_*.py` | tests of every candidate improvement (Cox, roster crowding, teammates, injury reports, tanking, recalibration, schedule, positions, ranges...); see the paper's Section 16 |
| `analysis/report_charts.py`, `analysis/report_pdf.py` | build the full PDF report, `docs/BPV-report.pdf` |

## Deploying

The `Procfile` runs the app with gunicorn. stats.nba.com often blocks or times out requests from cloud hosts (Heroku, AWS and others; see nba_api issues #182 and #320). A hosted copy may need a proxy (`nba_api` endpoints accept `proxy=`), or you can upload a pre-filled `data/cache/`.

## The live site

hoopothesis.cc runs on Render with `NBA_OFFLINE=1`: stats.nba.com doesn't answer cloud servers, so the site reads
`data/live/` and never calls the NBA. `refresh.py` keeps that folder current. A Windows scheduled task
("Hoopothesis data refresh") runs it at 8 AM and 6 PM. Each run:

1. Rebuilds the ratings with fresh data and copies the files the site reads into `data/live/`.
2. Logs and scores the in-season checks (`analysis/live_checks.py`, results in `data/tracking/` and on the home page):
   weekly projections vs a simple benchmark, injury-report play chances vs who actually played, and preseason
   projections for rookies and players returning from a missed season vs ESPN. A part doing worse than its
   benchmark on a fair sample is flagged; nothing changes the model by itself.
3. Checks before publishing: sanity checks on the ratings, and a full offline copy of the site run against
   `data/live/` exactly as the server will. If the code changed since the last verified deploy, it also runs the
   site in a Render-like Docker container (`deploy/Dockerfile`: Linux, gunicorn, 0.5 CPU, 512 MB) under
   keep-alive traffic like Render's proxy, so Docker Desktop needs to be running for code changes to go live.
   If anything fails it doesn't publish, so the live site keeps working data.
4. Commits, pushes, triggers a Render deploy, and confirms hoopothesis.cc is serving the new data.

Problems show up as a Windows notification and in `data/refresh.log`.
