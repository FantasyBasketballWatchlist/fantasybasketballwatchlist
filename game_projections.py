"""Single-game projections: each player's points, rebounds, assists, threes, etc. for his next game, with a full
spread of outcomes (so the chance of going over any line can be read off).

Rules: docs/prereg-game-projections.md (the first version, which failed its backtest) and
docs/prereg-game-projections-fix.md (the fixes, chosen on 2025-26 and tested once on 2024-25: more accurate than his
season average for every stat checked, honest 80% ranges; over/under chances not yet fully calibrated). In short: the
player's stat mix over his last 82 games, scaled so its ESPN fantasy points equal BPV's per-game projection, times
recent minutes, the opponent (per stat), back-to-back and home/away factors, shrunk part-way to his average for some
stats; game-to-game variance shrunk toward a league curve; negative binomial for counting stats, normal for fantasy
points. Projections are for the case that he plays (props on a player who doesn't play are void); the chance he plays
is given separately.

    python -m game_projections            (prints the next game day's top projections)
"""
import datetime
import math

import numpy as np
import pandas as pd

import bpv
import nba_data

BASE_STATS = ["PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV", "FGM", "FGA", "FTM", "FTA", "MIN"]
SHOWN = ["PTS", "REB", "AST", "FG3M", "PRA", "STL", "BLK", "TOV", "FPTS"]     # what the page and the checks use
COUNTS = {"PTS", "REB", "AST", "FG3M", "STL", "BLK", "TOV", "PRA"}            # negative binomial; FPTS is normal
LABELS = {"PTS": "Points", "REB": "Rebounds", "AST": "Assists", "FG3M": "Threes", "PRA": "Pts+Reb+Ast",
          "STL": "Steals", "BLK": "Blocks", "TOV": "Turnovers", "FPTS": "Fantasy pts (ESPN)"}
HISTORY_GAMES = 82          # his last 82 games: this season first, then last season
MIN_HISTORY = 5
VAR_K = 20                  # pseudo-games of the league variance curve
SCALE_RANGE = (0.5, 1.6)    # BPV anchor / stat-mix fantasy points
OPP_MIN_GAMES = 5           # opponent factor only once the opponent has played this many games
UNLISTED_PLAYS = 0.97       # not on the injury report
UNLISTED_SAT = 0.80         # not on the report, but his team has played since his last game
CURVE_MIN_GAMES = 20
OLD_OPP_COEF = 0.69         # ratings.WEEK_OPPONENT_COEF: the variance is scaled with the original fantasy-point factor
MIN_HALF_LIFE = 3           # recent minutes: averaged with a half-life of 3 games (analysis/game_fix.py, M1)
# Per stat, chosen on 2025-26 (analysis/game_fix.json "chosen"): w = weight of recent minutes, c = opponent coefficient,
# b2b = minutes factor on the second night of a back-to-back, home = +/- share at home / away, s = how much of the
# difference from his average is kept, k = variance multiplier.
# Second round (analysis/game_fix2.json, docs/prereg-game-projections-fix2.md): shape = "normal" with the variance x
# kshape for some counting stats (the negative binomial's long tail made it lean under against real lines), and
# alpha = share of a teammate's vacated minutes he picks up (teammate news from the day's injury report).
FIX = {
    "PTS":  {"w": 0.75, "c": 1.25, "b2b": 1.0, "home": 0.01, "s": 1.0, "k": 1.2, "alpha": 0.5, "shape": "normal", "kshape": 1.1},
    "REB":  {"w": 0.5, "c": 0.75, "b2b": 1.0,  "home": 0.0,   "s": 1.0, "k": 1.0, "alpha": 0.25},
    "AST":  {"w": 0.75, "c": 1.0, "b2b": 1.0,  "home": 0.01,  "s": 0.9, "k": 1.0, "alpha": 0.25},
    "FG3M": {"w": 0.5, "c": 0.75, "b2b": 1.0,  "home": 0.02,  "s": 0.8, "k": 1.1},
    "PRA":  {"w": 0.75, "c": 1.0, "b2b": 1.0,  "home": 0.0,   "s": 1.0, "k": 1.1, "alpha": 0.25, "shape": "normal", "kshape": 1.0},
    "STL":  {"w": 0.5, "c": 0.75, "b2b": 1.0,  "home": 0.0,   "s": 0.9, "k": 1.0},
    "BLK":  {"w": 0.5, "c": 0.5,  "b2b": 0.93, "home": 0.03,  "s": 0.8, "k": 1.0},
    "TOV":  {"w": 0.5, "c": 0.75, "b2b": 1.0,  "home": -0.01, "s": 0.9, "k": 0.9},
    "FPTS": {"w": 0.5, "c": 0.75, "b2b": 0.98, "home": 0.01,  "s": 1.0, "k": 1.1},
}


def with_combos(games):
    """Game logs plus FPTS (ESPN points scoring) and PRA."""
    g = bpv.add_fpts(games) if "FPTS" not in games else games.copy()
    g["PRA"] = g["PTS"] + g["REB"] + g["AST"]
    return g


def variance_curves(season_games):
    """Per stat, (a, b) in log(variance) = a + b log(mean), across players with CURVE_MIN_GAMES+ games in a season."""
    g = with_combos(season_games)
    per = g.groupby("PLAYER_ID")
    n = per.size()
    keep = n[n >= CURVE_MIN_GAMES].index
    curves = {}
    for s in SHOWN:
        m, v = per[s].mean().loc[keep], per[s].var().loc[keep]
        ok = (m > 0.05) & (v > 0)
        if ok.sum() < 30:
            curves[s] = (0.0, 1.0)
            continue
        b, a = np.polyfit(np.log(m[ok]), np.log(v[ok]), 1)
        curves[s] = (float(a), float(b))
    return curves


def opponent_relative(player_games, team_games):
    """Team -> {stat: what it allows per game relative to the league average}, for teams with OPP_MIN_GAMES+ games."""
    if player_games is None or team_games is None or not len(team_games) or "MATCHUP" not in team_games:
        return {}
    pg = with_combos(player_games)
    opp = team_games.assign(OPP=team_games["MATCHUP"].str[-3:])[["GAME_ID", "TEAM_ID", "OPP"]]
    allowed = pg.merge(opp, on=["GAME_ID", "TEAM_ID"]).groupby(["OPP", "GAME_ID"])[SHOWN].sum()
    per_team, games = allowed.groupby("OPP").mean(), allowed.groupby("OPP").size()
    if not len(per_team):
        return {}
    rel = per_team / per_team.mean()
    return {t: {st: float(rel.at[t, st]) for st in SHOWN} for t in rel.index if games[t] >= OPP_MIN_GAMES}


# ---------- distributions (no scipy: the live server doesn't install it)

def _nb_pmf(mean, var, kmax):
    """P(X = 0..kmax) for a negative binomial with this mean and variance (Poisson if var <= mean)."""
    if mean <= 0:
        return np.array([1.0] + [0.0] * kmax)
    if var <= mean * 1.0001:
        p = [math.exp(-mean)]
        for k in range(kmax):
            p.append(p[-1] * mean / (k + 1))
        return np.array(p)
    r = mean * mean / (var - mean)
    q = mean / (r + mean)                           # "success" share per trial
    p = [math.exp(r * math.log(1 - q))]
    for k in range(kmax):
        p.append(p[-1] * (k + r) / (k + 1) * q)
    return np.array(p)


def _norm_cdf(x, mean, sd):
    return 0.5 * (1 + math.erf((x - mean) / (sd * math.sqrt(2)))) if sd > 0 else float(x >= mean)


def cdf(dist, mean, var, x):
    """P(X <= x)."""
    if dist == "normal":
        return _norm_cdf(x, mean, math.sqrt(max(var, 1e-9)))
    k = math.floor(x)
    if k < 0:
        return 0.0
    return float(min(1.0, _nb_pmf(mean, var, k).sum()))


def p_over(dist, mean, var, line):
    """P(X > line). Half-point lines have no push; on a whole-number line, a push (X == line) counts as not over."""
    return 1.0 - cdf(dist, mean, var, line)


def quantile(dist, mean, var, q):
    if dist == "normal":
        lo, hi = mean - 8 * math.sqrt(var) - 1, mean + 8 * math.sqrt(var) + 1
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if _norm_cdf(mid, mean, math.sqrt(var)) < q else (lo, mid)
        return (lo + hi) / 2
    kmax = int(mean + 12 * math.sqrt(max(var, mean)) + 10)
    c = np.cumsum(_nb_pmf(mean, var, kmax))
    return float(np.searchsorted(c, q))


def pit(dist, mean, var, y):
    """Randomization-free PIT: mid-point of P(X < y) and P(X <= y) (for checking calibration)."""
    if dist == "normal":
        return _norm_cdf(y, mean, math.sqrt(max(var, 1e-9)))
    below = cdf(dist, mean, var, y - 1) if y >= 1 else 0.0
    return (below + cdf(dist, mean, var, y)) / 2


# ---------- the model

def dist_of(s):
    """'nb' or 'normal' for a stat (FPTS is always normal; some counting stats are normal since the second fix round)."""
    return "normal" if s not in COUNTS or FIX[s].get("shape") == "normal" else "nb"


def project_player(hist, anchor_fpts, curves, opp_rel=None, b2b=False, home=False, bench=None, vacated=0.0, share=0.0):
    """One player's projection. hist: his last games (BASE_STATS + FPTS + PRA, oldest first); opp_rel: the opponent's
    allowed-per-stat (None before it has played OPP_MIN_GAMES); bench: his average per stat (for the shrink);
    vacated / share: net minutes per game vacated by teammates' news today, and his share of the active teammates' minutes.
    Returns ({stat: {mean, var, dist}}, scale), or None if there's too little history."""
    n = len(hist)
    if n < MIN_HISTORY:
        return None
    mix_fpts = float(hist["FPTS"].mean())
    scale = anchor_fpts / mix_fpts if (anchor_fpts is not None and mix_fpts > 5) else 1.0
    scale = min(max(scale, SCALE_RANGE[0]), SCALE_RANGE[1])
    mins = hist["MIN"].to_numpy(float)
    weights = 0.5 ** (np.arange(n)[::-1] / MIN_HALF_LIFE)
    min_recent, min_mean = float((weights * mins).sum() / weights.sum()), float(mins.mean())
    f_old = scale * (1 + OLD_OPP_COEF * (opp_rel["FPTS"] - 1) if opp_rel else 1.0)
    out = {}
    for s in SHOWN:
        fx = FIX[s]
        oppf = 1 + fx["c"] * (opp_rel[s] - 1) if opp_rel else 1.0
        minf = (fx["w"] * min_recent + (1 - fx["w"]) * min_mean) / min_mean if min_mean > 1 else 1.0
        minf *= fx["b2b"] if b2b else 1.0
        homef = 1 + fx["home"] if home else 1 - fx["home"]
        mix = float(hist[s].mean())
        mean = mix * scale * oppf * minf * homef
        b = bench.get(s) if bench else None
        if b is not None:
            mean = b + fx["s"] * (mean - b)
        if s != "FPTS":
            mean = max(0.0, mean)
        v_emp = float(hist[s].var()) * f_old * f_old if n > 1 else 0.0
        a, bb = curves.get(s, (0.0, 1.0))
        v_league = math.exp(a + bb * math.log(max(mean, 0.05)))
        var = (n * v_emp + VAR_K * v_league) / (n + VAR_K) * fx["k"]
        if fx.get("alpha") and vacated:
            mh = fx["w"] * min_recent + (1 - fx["w"]) * min_mean
            if mh > 1:
                mean = max(0.0, mean * (mh + fx["alpha"] * vacated * share) / mh)
        dist = dist_of(s)
        if dist == "normal" and s in COUNTS:
            var *= fx.get("kshape", 1.0)
        out[s] = {"mean": mean, "var": max(var, 1e-6), "dist": dist}
    return out, scale


def play_chance(status, team_played_since):
    if status:
        return bpv.PLAY_PROBABILITY.get(status)
    return UNLISTED_SAT if team_played_since else UNLISTED_PLAYS


def summarize(stats):
    """Add the 10th/50th/90th percentiles (for display and logging)."""
    for s, d in stats.items():
        d["q10"], d["q50"], d["q90"] = (quantile(d["dist"], d["mean"], d["var"], q) for q in (0.1, 0.5, 0.9))
    return stats


def last_games(this_season, last_season):
    """Player id -> his last HISTORY_GAMES games (newest last), from this season then last season."""
    frames = [x for x in (last_season, this_season) if x is not None and len(x)]
    if not frames:
        return {}
    g = with_combos(pd.concat(frames, ignore_index=True)).sort_values(["GAME_DATE", "GAME_ID"])
    return {pid: grp.tail(HISTORY_GAMES) for pid, grp in g.groupby("PLAYER_ID")}


NEWS_STATUSES = {"Out", "Doubtful"}
RETURN_MPG = 15


def teammate_news(games, listed_by_team, day, teams):
    """Player id -> (net vacated minutes, his share of the active teammates' minutes) for `teams` playing on `day`,
    as in analysis/game_fix2.py: new absences = teammates listed Out/Doubtful today who played the team's previous game;
    returns = teammates with 15+ minutes a game who missed it, are still with the team (latest game for it within 15
    days) and aren't listed. Minutes per game over each player's last 10 of the team's last 10 games."""
    g = games[(games["MIN"] > 0) & (games["GAME_DATE"] < day)]
    out = {}
    cutoff = (datetime.date.fromisoformat(day) - datetime.timedelta(days=15)).isoformat()
    latest = g.sort_values("GAME_DATE").groupby("PLAYER_ID").tail(1).set_index("PLAYER_ID")
    for team in teams:
        dates = sorted(set(g[g["TEAM_ABBREVIATION"] == team]["GAME_DATE"]))[-10:]
        if not dates:
            continue
        hist = g[(g["TEAM_ABBREVIATION"] == team) & g["GAME_DATE"].isin(dates)]
        mpg = hist.groupby("PLAYER_ID")["MIN"].apply(lambda m: m.tail(10).mean())
        played_prev = set(hist[hist["GAME_DATE"] == dates[-1]]["PLAYER_ID"])
        recent3 = set(hist[hist["GAME_DATE"].isin(dates[-3:])]["PLAYER_ID"])
        listed = listed_by_team.get(team, set())
        on_team = {pid for pid in mpg.index if pid in latest.index and latest.at[pid, "TEAM_ABBREVIATION"] == team
                   and latest.at[pid, "GAME_DATE"] >= cutoff}
        new_abs = [pid for pid in mpg.index if pid in played_prev and pid in listed]
        returns = [pid for pid in mpg.index if pid not in played_prev and pid in on_team and mpg[pid] >= RETURN_MPG and pid not in listed]
        v = float(mpg[new_abs].sum() - mpg[returns].sum())
        active = [pid for pid in mpg.index if (pid in recent3 or pid in returns) and pid in (on_team | played_prev) and pid not in listed]
        act = float(mpg[active].sum()) if active else 0.0
        for pid in mpg.index:
            out[int(pid)] = (v, float(mpg[pid]) / act if act > 0 else 0.0)
    return out


def next_game_day(schedule, today):
    upcoming = schedule[schedule["GAME_DATE"] >= today.isoformat()]
    return upcoming["GAME_DATE"].min() if len(upcoming) else None


def project_day(players, hist_by_pid, curves, schedule, day, opp_rel, last_team_game, last_player_game,
                played_yesterday=(), bench=None, news=None):
    """Projections for everyone in `players` (id, name, team, production, report_status) whose team plays on `day`."""
    games = schedule[schedule["GAME_DATE"] == day]
    opp_of = {r.TEAM_ABBREVIATION: (r.OPPONENT, bool(r.HOME)) for r in games.itertuples()}
    bench = bench or {}
    rows = []
    for p in players.itertuples():
        if p.team not in opp_of:
            continue
        hist = hist_by_pid.get(p.id)
        if hist is None:
            continue
        opp, home = opp_of[p.team]
        v, sh = (news or {}).get(p.id, (0.0, 0.0))
        res = project_player(hist, getattr(p, "production", None), curves, opp_rel.get(opp), p.team in played_yesterday,
                             home, bench.get(p.id), v, sh)
        if res is None:
            continue
        stats, scale = res
        status = getattr(p, "report_status", None)
        status = status if isinstance(status, str) and status else None
        sat = last_team_game.get(p.team, "") > last_player_game.get(p.id, "")
        rows.append({"id": int(p.id), "name": p.name, "team": p.team, "opp": opp, "home": home, "status": status,
                     "play_probability": play_chance(status, sat), "sat_last": bool(sat), "scale": round(scale, 3),
                     "b2b": p.team in played_yesterday, "minutes": round(float(hist["MIN"].mean()) * scale, 1),
                     "history_games": len(hist), "teammate_minutes": round(v, 1), "stats": summarize(stats)})
    return rows


def today(players=None, meta=None, day=None):
    """Live: projections for the next game day (from today, US Eastern), using the site's ratings."""
    import ratings
    if players is None:
        players, meta = ratings.get()
    season = meta["season"]
    seasons = [nba_data.previous_season(season), season]
    this_g = nba_data.player_game_logs(season)
    last_g = nba_data.player_game_logs(seasons[0])
    sched = nba_data.schedule(meta.get("target_season") or season)
    now_et = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(hours=4)
    day = day or next_game_day(sched, now_et.date())
    if day is None:
        return {"day": None, "games": [], "players": []}
    try:
        team_games = nba_data.team_game_logs(season)
    except Exception:
        team_games = None
    curves = variance_curves(last_g)
    hist = last_games(this_g, last_g)
    tg = team_games if team_games is not None else pd.DataFrame(columns=["TEAM_ABBREVIATION", "GAME_DATE"])
    last_team = tg.groupby("TEAM_ABBREVIATION")["GAME_DATE"].max().to_dict() if len(tg) else {}
    last_player = this_g.groupby("PLAYER_ID")["GAME_DATE"].max().to_dict() if len(this_g) else {}
    opp = opponent_relative(this_g, team_games)
    yday = (datetime.date.fromisoformat(day) - datetime.timedelta(days=1)).isoformat()
    played_yday = set(tg[tg["GAME_DATE"] == yday]["TEAM_ABBREVIATION"]) if len(tg) else set()
    bench = benchmark(this_g[this_g["GAME_DATE"] < day] if len(this_g) else this_g, last_g)
    listed = {}
    if "report_status" in players:
        for r in players[players["report_status"].isin(NEWS_STATUSES)].itertuples():
            listed.setdefault(r.team, set()).add(int(r.id))
    playing = set(sched[sched["GAME_DATE"] == day]["TEAM_ABBREVIATION"])
    news = teammate_news(this_g, listed, day, playing) if len(this_g) else {}
    rows = project_day(players, hist, curves, sched, day, opp, last_team, last_player, played_yday, bench, news)
    for r in rows:
        r["bench"] = {st: round(v, 2) for st, v in bench.get(r["id"], {}).items()}
    games = sched[(sched["GAME_DATE"] == day) & (sched["HOME"].astype(bool))]
    return {"day": day, "games": [{"home": r.TEAM_ABBREVIATION, "away": r.OPPONENT} for r in games.itertuples()],
            "players": sorted(rows, key=lambda r: -r["stats"]["FPTS"]["mean"]), "labels": LABELS, "stats": SHOWN}


if __name__ == "__main__":
    import os
    os.environ.setdefault("NBA_OFFLINE", "1")
    out = today()
    print(out["day"], len(out["games"]), "games", len(out["players"]), "players")
    for r in out["players"][:12]:
        s = r["stats"]
        print(f"{r['name']:<26} {r['team']} v {r['opp']}  play {r['play_probability']:.2f}  "
              + "  ".join(f"{k} {s[k]['mean']:.1f} [{s[k]['q10']:.0f}-{s[k]['q90']:.0f}]" for k in ("PTS", "REB", "AST", "FG3M", "FPTS")))


# ---------- logging and scoring (shared by analysis/live_checks.py and analysis/game_backtest.py)

def benchmark(this_before, last_season):
    """Player id -> {stat: simple benchmark}: his average this season before the day, or last season's if he has fewer
    than 3 games this season."""
    out = {}
    tb = with_combos(this_before) if this_before is not None and len(this_before) else None
    ls = with_combos(last_season) if last_season is not None and len(last_season) else None
    cur = tb.groupby("PLAYER_ID") if tb is not None else None
    n = cur.size() if cur is not None else pd.Series(dtype=int)
    cur_mean = cur[SHOWN].mean() if cur is not None else pd.DataFrame(columns=SHOWN)
    last_mean = ls.groupby("PLAYER_ID")[SHOWN].mean() if ls is not None else pd.DataFrame(columns=SHOWN)
    for pid in set(cur_mean.index) | set(last_mean.index):
        src = cur_mean if (pid in n.index and n[pid] >= 3) or pid not in last_mean.index else last_mean
        out[pid] = {s: float(src.at[pid, s]) for s in SHOWN}
    return out


def flatten(day, row, bench):
    """One projection as a flat record for logging: per stat its mean, variance, 10th/90th percentiles, the benchmark,
    the proxy line (benchmark rounded down + 0.5) and the model's chance of the over."""
    rec = {"date": day, "id": row["id"], "name": row["name"], "team": row["team"], "opp": row["opp"],
           "status": row.get("status") or "", "play_probability": row["play_probability"], "sat_last": row.get("sat_last", False)}
    for s in SHOWN:
        d = row["stats"][s]
        b = bench.get(s) if bench else None
        line = math.floor(b) + 0.5 if b is not None else None
        # The 10th/90th percentiles aren't stored: score() recomputes them from the mean and variance.
        rec.update({f"{s}_mean": round(d["mean"], 3), f"{s}_var": round(d["var"], 3),
                    f"{s}_bench": round(b, 2) if b is not None else None, f"{s}_line": line,
                    f"{s}_pover": round(p_over(d["dist"], d["mean"], d["var"], line), 4) if line is not None else None})
    return rec


BUCKETS = [0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 1.01]


def score(log, games):
    """Score logged projections against the box scores (players who played). log: flatten() records; games: game logs.
    Returns per-stat accuracy, range coverage and proxy-line calibration, with the pass rules of the preregistration."""
    if log is None or not len(log):
        return {"status": "nothing logged yet"}
    g = with_combos(games)
    g = g[g["MIN"] > 0]
    actual = g.set_index(["PLAYER_ID", "GAME_DATE"])[SHOWN]
    log = log.copy()
    keys = list(zip(log["id"].astype(int), log["date"]))
    have = [k in actual.index for k in keys]
    done = log[have].copy()
    if not len(done):
        return {"status": "waiting for games", "logged": int(len(log))}
    act = actual.loc[[k for k, h in zip(keys, have) if h]].reset_index(drop=True)
    done = done.reset_index(drop=True)
    out = {"status": "scored", "player_games": int(len(done)), "game_days": int(done["date"].nunique()), "stats": {}}
    for s in SHOWN:
        y = act[s].astype(float)
        mean, bench = done[f"{s}_mean"].astype(float), done[f"{s}_bench"].astype(float)
        ok = bench.notna()
        dist = dist_of(s)
        q10 = [quantile(dist, m_, v_, 0.1) for m_, v_ in zip(mean, done[f"{s}_var"].astype(float))]
        q90 = [quantile(dist, m_, v_, 0.9) for m_, v_ in zip(mean, done[f"{s}_var"].astype(float))]
        inside = ((y >= q10) & (y <= q90)).mean()
        # Check 2b (docs/prereg-game-projections-fix.md): randomized PIT between 0.1 and 0.9, 80% for an honest forecast.
        rng = np.random.default_rng(11)
        pits = []
        for m_, v_, y_ in zip(mean, done[f"{s}_var"].astype(float), y):
            hi = cdf(dist, m_, v_, y_)
            lo = (cdf(dist, m_, v_, y_ - 1) if y_ >= 1 else 0.0) if dist != "normal" else hi
            pits.append(lo + rng.random() * (hi - lo))
        pits = np.array(pits)
        res = {"n": int(len(y)), "mae": float((mean - y).abs().mean()), "mae_bench": float((bench[ok] - y[ok]).abs().mean()) if ok.any() else None,
               "inside_80": float(inside), "pit_80": float(((pits > 0.1) & (pits < 0.9)).mean())}
        pv, line = done[f"{s}_pover"].astype(float), done[f"{s}_line"].astype(float)
        m = pv.notna() & line.notna()
        if m.any():
            # Each bet: the side the model favours, with its chance; did it win?
            p_side = np.where(pv[m] >= 0.5, pv[m], 1 - pv[m])
            won = np.where(pv[m] >= 0.5, y[m] > line[m], y[m] < line[m])
            buckets = []
            for lo, hi in zip(BUCKETS[:-1], BUCKETS[1:]):
                b = (p_side >= lo) & (p_side < hi)
                if b.any():
                    buckets.append({"from": lo, "to": min(hi, 1.0), "n": int(b.sum()), "predicted": float(p_side[b].mean()),
                                    "actual": float(won[b].mean())})
            over = (y[m] > line[m]).astype(float)
            res["lines"] = {"n": int(m.sum()), "brier": float(((pv[m] - over) ** 2).mean()), "brier_50": float(((0.5 - over) ** 2).mean()),
                            "buckets": buckets}
        out["stats"][s] = res
    unl = log[log["status"].fillna("") == ""]
    plays = {}
    for flag, grp in unl.groupby(unl["sat_last"].astype(bool)):
        k = [(int(i), d) for i, d in zip(grp["id"], grp["date"])]
        played = [x in actual.index for x in k]
        plays["sat last game" if flag else "played last game"] = {"n": len(k), "predicted": float(grp["play_probability"].mean()),
                                                                   "actual": float(np.mean(played)) if k else None}
    out["plays"] = plays
    out["passes"] = passes(out)
    return out


def passes(out, min_days=14, min_games=1000):
    """The preregistered pass rules (None while there's too little to judge)."""
    if out.get("game_days", 0) < min_days or out.get("player_games", 0) < min_games:
        return {"judged": False}
    st = out["stats"]
    better = {s: st[s]["mae_bench"] is not None and st[s]["mae"] < st[s]["mae_bench"] for s in ("FPTS", "PTS", "REB", "AST")}
    accuracy = better["FPTS"] and sum(better[s] for s in ("PTS", "REB", "AST")) >= 2
    ranges = all(0.75 <= st[s]["pit_80"] <= 0.85 for s in SHOWN)        # check 2b
    lines = all(all(abs(b["predicted"] - b["actual"]) <= 0.05 for b in st[s]["lines"]["buckets"] if b["n"] >= 100)
                and st[s]["lines"]["brier"] < st[s]["lines"]["brier_50"] for s in SHOWN if "lines" in st[s])
    return {"judged": True, "accuracy": accuracy, "accuracy_by_stat": better, "ranges": ranges, "lines": lines}
