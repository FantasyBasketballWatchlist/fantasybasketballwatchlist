"""BPV in season vs FantasyPros' rest-of-season expert consensus (rules fixed beforehand in docs/prereg-ros-experts.md).

Reads archived FantasyPros ROS ranking pages (Wayback captures, downloaded into a folder given on the command line),
rebuilds the app's ratings on each capture date, and scores BPV, the experts and their rank average against what
happened for the rest of the season. Writes analysis/ros_experts.json.

    python -m analysis.ros_experts <folder of <season>_<timestamp>.html captures>
"""
import datetime
import glob
import html
import json
import os
import re
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ["NBA_OFFLINE"] = "1"

import bpv   # noqa: E402
import nba_data   # noqa: E402
import ratings   # noqa: E402
from analysis import test_espn_projections as te   # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ros_experts.json")
POOL, MISSING_RANK, BOOT = 150, 200, 5000


def parse(path):
    """[(rank, name)] from an archived FantasyPros ROS page (old HTML table or embedded ecrData), or None."""
    h = open(path, encoding="utf-8", errors="replace").read()
    heading = re.search(r'"page_heading":"([^"]+)"', h) or re.search(r"<h1[^>]*>(.*?)</h1>", h, re.S)
    head = html.unescape(re.sub(r"<[^>]+>", " ", heading.group(1))) if heading else ""
    m = re.search(r"var ecrData = (\{.*?\});\s*\n", h, re.S)
    if m:
        data = json.loads(m.group(1))
        if "season" in data.get("type", "").lower() or data.get("ranking_type_name") == "ros":
            return [(int(p["rank_ecr"]), p["player_name"]) for p in data["players"]], head
        return None, head
    rows = re.findall(r'<tr class="mpb-player-\d+"><td>(\d+)</td>.*?class="player-name">([^<]+)</a>', h, re.S)
    # Old pages: the first <h1> is the site's "Notifications" panel, so the page <title> says what the list is.
    title = re.search(r"<title>(.*?)</title>", h, re.S)
    head = html.unescape(title.group(1)).strip() if title else head
    if rows and "rest of season" in head.lower():
        return [(int(r), html.unescape(n)) for r, n in rows], head
    return None, head


def realized(games, sched, pid, date, repl):
    """FPTS per remaining team game from rostering him: his games plus a streamed replacement in 5+ game absences."""
    g = games.get(pid)
    if g is None:
        return None
    before = g[g["GAME_DATE"] < date]
    team = before["TEAM_ABBREVIATION"].iloc[-1] if len(before) else g["TEAM_ABBREVIATION"].iloc[0]
    left = [x for x in sched.get(team, []) if x >= date]
    if len(left) < 10:
        return None
    played = set(g[(g["GAME_DATE"] >= date) & (g["TEAM_ABBREVIATION"] == team)]["GAME_DATE"])
    run = streamed = 0
    for x in left + [None]:
        if x is not None and x not in played:
            run += 1
            continue
        if run >= bpv.LONG_ABSENCE_GAMES:
            streamed += run
        run = 0
    return (g[g["GAME_DATE"].isin(played)]["FPTS"].sum() + streamed * repl) / len(left)


def score_date(season, ts, ecr):
    date = datetime.date(int(ts[:4]), int(ts[4:6]), int(ts[6:8]))
    full_p, full_t = bpv.add_fpts(nba_data.player_game_logs(season)), nba_data.team_game_logs(season)
    reports = nba_data.injury_reports(season)
    op, ot, orr = nba_data.player_game_logs, nba_data.team_game_logs, nba_data.recent_injury_reports
    os.environ["NBA_SEASON"] = season
    try:
        cut = lambda f: (lambda s: (lambda df: df[df["GAME_DATE"] < date.isoformat()] if s == season else df)(f(s)))
        nba_data.player_game_logs, nba_data.team_game_logs = cut(op), cut(ot)
        start = (date - datetime.timedelta(days=4)).isoformat()
        nba_data.recent_injury_reports = lambda *a, **k: reports[(reports["REPORT_DATE"] >= start)
                                                                & (reports["REPORT_DATE"] < date.isoformat())].copy()
        ratings._season_started = lambda *a: True
        df, meta = ratings.build(today=date)
    finally:
        nba_data.player_game_logs, nba_data.team_game_logs, nba_data.recent_injury_reports = op, ot, orr
        os.environ.pop("NBA_SEASON", None)
    df = df.assign(key=df["name"].map(te.key))
    ecr_rank = {}
    for r, n in ecr:
        ecr_rank.setdefault(te.key(n), r)
    df["ecr"] = df["key"].map(ecr_rank)
    pool = df[(df["rank"] <= POOL) | (df["ecr"] <= POOL)].copy()
    games = {p: g.sort_values("GAME_DATE") for p, g in full_p.groupby("PLAYER_ID")}
    sched = {t: sorted(d) for t, d in full_t.groupby("TEAM_ABBREVIATION")["GAME_DATE"]}
    pool["real"] = [realized(games, sched, p, date.isoformat(), meta["replacement_level"]) for p in pool["id"]]
    pool = pool.dropna(subset=["real"])
    pool["ecr_r"] = pool["ecr"].fillna(MISSING_RANK)
    pool["blend_r"] = (pool["rank"].clip(upper=MISSING_RANK) + pool["ecr_r"]) / 2
    corr = lambda col, sign: pool[col].mul(sign).rank().corr(pool["real"].rank())
    return {"season": season, "date": date.isoformat(), "pool": int(len(pool)),
            "ecr_matched_in_pool": int(pool["ecr"].notna().sum()),
            "bpv": corr("bpv", 1), "ecr": corr("ecr_r", -1), "blend": corr("blend_r", -1)}


def compare(rows, a, b):
    d = rows[a] - rows[b]
    rng = np.random.default_rng(7)
    boots = [d.sample(len(d), replace=True, random_state=rng.integers(1 << 31)).mean() for _ in range(BOOT)]
    seasons = rows.assign(d=d).groupby("season")["d"].mean()
    return {"mean_diff": float(d.mean()), "ci": [float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))],
            "dates_better": f"{int((d > 0).sum())} of {len(d)}",
            "by_season": {s: round(float(v), 4) for s, v in seasons.items()},
            "seasons_better": f"{int((seasons > 0).sum())} of {len(seasons)}",
            "passes": bool(np.percentile(boots, 2.5) > 0 and (seasons > 0).mean() >= 0.6)}


def main():
    folder = sys.argv[1]
    rows, skipped = [], []
    for path in sorted(glob.glob(os.path.join(folder, "*.html"))):
        season, ts = os.path.basename(path)[:-5].split("_")
        ecr, head = parse(path)
        if not ecr or len(ecr) < 100:
            skipped.append({"capture": os.path.basename(path), "heading": head[:80], "players": len(ecr or [])})
            continue
        r = score_date(season, ts, ecr)
        r["heading"] = head[:80]
        rows.append(r)
        print(r["date"], r["pool"], "bpv %.3f ecr %.3f blend %.3f" % (r["bpv"], r["ecr"], r["blend"]), flush=True)
    rows = pd.DataFrame(rows)
    out = {"rules": "docs/prereg-ros-experts.md", "dates": int(len(rows)), "skipped": skipped,
           "mean": {k: float(rows[k].mean()) for k in ("bpv", "ecr", "blend")},
           "blend_vs_bpv": compare(rows, "blend", "bpv"), "ecr_vs_bpv": compare(rows, "ecr", "bpv"),
           "blend_vs_ecr": compare(rows, "blend", "ecr"), "per_date": rows.to_dict(orient="records")}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: v for k, v in out.items() if k != "per_date"}, indent=1))


if __name__ == "__main__":
    main()
