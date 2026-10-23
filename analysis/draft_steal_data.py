"""Inputs for the steal replay (analysis/draft_steal_replay.js) and calibration (analysis/draft_steal_calib.py).

    python -m analysis.draft_steal_data <out dir>

Writes <out dir>/players.json (the site's /api/rankings and /api/positions, offline data) and <out dir>/leagues.json
(the six public ESPN leagues' real draft orders, docs/prereg-draft-steal.md).
"""
import json
import os
import sys

import requests

os.environ.setdefault("NBA_OFFLINE", "1")
os.environ.setdefault("NBA_CACHE_DIR", "data/live")

LEAGUES = ["538977698", "1854297225", "1503540199", "34650931", "1192115637", "2029687819"]
API = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fba/seasons/2027"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def main(out):
    import app
    c = app.app.test_client()
    r, p = c.get("/api/rankings?limit=2000").get_json(), c.get("/api/positions").get_json()
    json.dump({"players": r["players"], "positions": p["positions"]}, open(os.path.join(out, "players.json"), "w"))
    f = {"players": {"limit": 1500, "sortPercOwned": {"sortAsc": False, "sortPriority": 1}}}
    names = {x["player"]["id"]: x["player"]["fullName"] for x in requests.get(
        f"{API}/segments/0/leaguedefaults/3?view=kona_player_info", headers={**HEADERS, "X-Fantasy-Filter": json.dumps(f)},
        timeout=30).json()["players"]}
    leagues = {}
    for lg in LEAGUES:
        d = requests.get(f"{API}/segments/0/leagues/{lg}", params=[("view", "mDraftDetail"), ("view", "mTeam")],
                         headers=HEADERS, timeout=30).json()
        picks = sorted(d["draftDetail"]["picks"], key=lambda x: x["overallPickNumber"])
        leagues[lg] = {"teams": len(d["teams"]),
                       "picks": [[x["overallPickNumber"], names.get(x["playerId"], str(x["playerId"]))] for x in picks]}
    json.dump(leagues, open(os.path.join(out, "leagues.json"), "w"))


if __name__ == "__main__":
    main(sys.argv[1])
