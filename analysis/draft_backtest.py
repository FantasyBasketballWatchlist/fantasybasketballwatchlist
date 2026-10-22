"""The draft suggestion on past seasons, scored by real games (rules: docs/prereg-draft-backtest.md).

    python -m analysis.draft_backtest prep     (writes static/_bt_players_<season>.json for the browser run; delete after)
    python -m analysis.draft_backtest score    (reads analysis/draft_backtest_rosters.json, writes analysis/draft_backtest.json)

The drafts run in the browser on the draft page's own engine (lookAhead) with each season's players swapped in.
"""
import json
import math
import os
import sys
import warnings

import numpy as np

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import bpv   # noqa: E402
import nba_data   # noqa: E402
from analysis import backtest as bt   # noqa: E402
from analysis import test_espn_projections as te_   # noqa: E402
from analysis import test_ten_team as ttt   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTERS = os.path.join(ROOT, "analysis", "draft_backtest_rosters.json")
OUT = os.path.join(ROOT, "analysis", "draft_backtest.json")
SLOT_POS = {0: "PG", 1: "SG", 2: "SF", 3: "PF", 4: "C"}
SLOTS = "PG,SG,SF,PF,C,G,F,UTIL,UTIL,UTIL".split(",")
HYBRID = "BPV + ESPN hybrid (app)"


def positions(year, names):
    out = {}
    for p in te_.fetch(year)["players"]:
        pl = p["player"]
        ps = [SLOT_POS[s] for s in sorted(pl.get("eligibleSlots", [])) if s in SLOT_POS]
        pid = names.get(te_.key(pl["fullName"]))
        if ps and pid is not None:
            out[int(pid)] = "/".join(ps)
    return out


def prep():
    pg, tg = bt.load()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, nba_data.draft_history())
    league_p, league_q = bpv.league_availability(hist)
    names = te_.name_map(pg)
    for t, year in te_.ESPN_SEASONS.items():
        df = ttt.season_frame(pg, tg, hist, league_p, league_q, t, names)
        df = df[np.isfinite(df[HYBRID])]
        pos = positions(year, names)
        rows = []
        for pid, r in df.iterrows():
            espn = r[ttt.ESPN]
            rows.append({"id": int(pid), "name": str(r.get("name", pid)), "bpv": float(r[HYBRID]),
                         "production": float(r.hybrid_production), "availability": float(min(1, max(0, r.hybrid_availability))),
                         "espn": float(espn) if np.isfinite(espn) else None, "pos": pos.get(int(pid), "")})
        with open(os.path.join(ROOT, "static", f"_bt_players_{t}.json"), "w", encoding="utf-8") as f:
            json.dump(rows, f)
        print(t, len(rows), "players,", sum(bool(r["pos"]) for r in rows), "with positions,",
              sum(r["espn"] is not None for r in rows), "with ESPN", flush=True)


def fits(slot, ps):
    if slot == "UTIL":
        return True
    if slot == "G":
        return "PG" in ps or "SG" in ps
    if slot == "F":
        return "SF" in ps or "PF" in ps
    return slot in ps


def season_score(roster, games, value, pos):
    """Sum over dates of the starters' actual FPTS; starters chosen by preseason value (known in advance)."""
    by_date = games[games.PLAYER_ID.isin(roster)].groupby("GAME_DATE")
    total = 0.0
    for _, day in by_date:
        players = sorted(day.itertuples(), key=lambda r: -value[r.PLAYER_ID])
        owner = [None] * len(SLOTS)

        def place(r, seen):
            ps = pos.get(r.PLAYER_ID, [])
            for i, slot in enumerate(SLOTS):
                if seen[i] or not fits(slot, ps):
                    continue
                seen[i] = True
                if owner[i] is None or place(owner[i], seen):
                    owner[i] = r
                    return True
            return False
        for r in players:
            if place(r, [False] * len(SLOTS)):
                total += r.FPTS
    return total


def score():
    rosters = json.load(open(ROSTERS, encoding="utf-8"))
    res = {"rules": "docs/prereg-draft-backtest.md", "seasons": {}}
    per = {}
    for t, by_variant in rosters.items():
        games = bpv.add_fpts(nba_data.player_game_logs(t))
        games = games[games.MIN > 0]
        players = json.load(open(os.path.join(ROOT, "static", f"_bt_players_{t}.json"), encoding="utf-8"))
        value = {p["id"]: p["bpv"] for p in players}
        pos = {p["id"]: p["pos"].split("/") if p["pos"] else [] for p in players}
        totals = games.groupby("PLAYER_ID").FPTS.sum()
        res["seasons"][t] = {}
        for v, seats in by_variant.items():
            s = [season_score(r, games, value, pos) for r in seats.values()]
            b10 = [float(sorted((totals.get(i, 0.0) for i in r), reverse=True)[:10] and sum(sorted((totals.get(i, 0.0) for i in r), reverse=True)[:10])) for r in seats.values()]
            guards = [sum(any(x in ("PG", "SG") for x in pos.get(i, [])) for i in r) for r in seats.values()]
            per.setdefault(v, {})[t] = s
            res["seasons"][t][v] = {"season_score": float(np.mean(s)), "best10_total": float(np.mean(b10)),
                                    "guards_of_13": float(np.mean(guards)), "by_seat": [round(x, 1) for x in s]}
        print(t, {v: round(res["seasons"][t][v]["season_score"]) for v in by_variant}, flush=True)

    def compare(a, b):
        d = {t: float(np.mean(np.array(per[a][t]) - np.array(per[b][t]))) for t in per[a]}
        mean = float(np.mean([x for t in per[a] for x in np.array(per[a][t]) - np.array(per[b][t])]))
        return {"mean_gain": mean, "per_season": d, "seasons_better": int(sum(x > 0 for x in d.values())),
                "passes": bool(mean > 0 and sum(x > 0 for x in d.values()) >= 3)}
    res["engine_vs_best_bpv"] = compare("engine", "best_bpv")
    res["engine_vs_espn"] = compare("engine", "espn")
    for v in ("A", "B"):
        if v in per:
            res[f"{v}_vs_engine"] = compare(v, "engine")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(json.dumps({k: v for k, v in res.items() if k != "seasons"}, indent=1))


if __name__ == "__main__":
    {"prep": prep, "score": score}[sys.argv[1]]()
