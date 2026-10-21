"""The preregistered bet-selection rule set (docs/prereg-real-lines-rules.md), for one season of saved lines.

    python -m analysis.real_lines_rules 2024-25                  (design reference: data/lines/history.csv, spreads.csv)
    python -m analysis.real_lines_rules 2023-24 --lines data/lines/history_2023-24.csv --spreads data/lines/spreads_2023-24.csv

Writes analysis/real_lines_rules_<season>.json (results only, no raw lines).
"""
import argparse
import json
import os
import warnings

import numpy as np
import pandas as pd
from scipy import stats as sst

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

import nba_data   # noqa: E402
from analysis import game_fix as gf   # noqa: E402
from analysis import real_lines as rl   # noqa: E402

ROOT = rl.ROOT
STATS = ["PTS", "REB", "AST"]
VAR_MULT = 1.4
BLEND_W = {"PTS": 0.10, "REB": 0.20, "AST": 0.30}
MIN_EV = 0.03
MAX_GAP = 0.15
BLOWOUT_SPREAD = 12
ROTATION_MPG = 20
NEWS_STATUSES = {"Out", "Doubtful", "Questionable"}
# R1 shops only US state-licensed books (offshore books such as Bovada / BetOnline aren't legal in US states).
LICENSED = {"draftkings", "fanduel", "betmgm", "williamhill_us", "betrivers", "espnbet", "fanatics", "ballybet",
            "hardrockbet", "betparx"}
logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
expit = lambda x: 1 / (1 + np.exp(-x))


def team_maps():
    from nba_api.stats.static import teams
    t = teams.get_teams()
    return {x["full_name"]: x["abbreviation"] for x in t}


def consensus(lines):
    """Per game/player/stat at the line most books offer: median and best decimal price per side."""
    lines = lines.assign(dec=rl.decimal(lines["price"]))
    rows = []
    for (gd, ev, player, stat), g in lines.groupby(["game_date", "event_id", "player", "stat"]):
        books = g.groupby("line")["bookmaker"].nunique()
        line = books[books == books.max()].index.min()
        at = g[g["line"] == line]
        o, u = at[at["side"] == "Over"]["dec"], at[at["side"] == "Under"]["dec"]
        lic = at[at["bookmaker"].isin(LICENSED)]
        lo, lu = lic[lic["side"] == "Over"]["dec"], lic[lic["side"] == "Under"]["dec"]
        if not len(o) or not len(u) or not len(lo) or not len(lu):
            continue
        rows.append({"game_date": gd, "event_id": ev, "home": g["home"].iloc[0], "away": g["away"].iloc[0], "player": player,
                     "stat": stat, "line": float(line), "med_over": float(np.median(o)), "med_under": float(np.median(u)),
                     "best_over": float(lo.max()), "best_under": float(lu.max())})
    return pd.DataFrame(rows)


def news_games(season, cons, games, abbr):
    """Event ids with fresh injury news: a rotation player (20+ min over his last 10) who played his team's previous
    game is listed Out / Doubtful / Questionable on the game day's report."""
    rep = nba_data.injury_reports(season)
    rep = rep[rep["Current Status"].isin(NEWS_STATUSES)].copy()
    rep["date"] = pd.to_datetime(rep["Game Date"], format="%m/%d/%Y").dt.strftime("%Y-%m-%d")
    rep = rep[rep["REPORT_DATE"] == rep["date"]]
    def flip(n):
        n = str(n)
        if "," in n:
            last, first = n.split(",", 1)
            n = f"{first.strip()} {last.strip()}"
        return rl.key(n)
    rep["key"] = rep["Player Name"].map(flip)
    g = games.copy()
    g["key"] = g["PLAYER_NAME"].map(rl.key)
    flagged = set()
    by_team_dates = g.groupby("TEAM_ABBREVIATION")["GAME_DATE"].apply(lambda s: sorted(set(s))).to_dict()
    for ev in cons.drop_duplicates("event_id").itertuples():
        day = ev.game_date
        for full in (ev.home, ev.away):
            team = abbr.get(full)
            r = rep[(rep["date"] == day) & (rep["Team"] == full)]
            if r.empty or team is None:
                continue
            prev = [d for d in by_team_dates.get(team, []) if d < day]
            if not prev:
                continue
            last_day = prev[-1]
            for k in r["key"]:
                pg = g[(g["key"] == k) & (g["GAME_DATE"] < day)].tail(10)
                if len(pg) and pg["MIN"].mean() >= ROTATION_MPG and (pg["GAME_DATE"] == last_day).any():
                    flagged.add(ev.event_id)
                    break
            if ev.event_id in flagged:
                break
    return flagged


def evaluate(season, prior, lines_path, spreads_path):
    abbr = team_maps()
    lines = pd.read_csv(lines_path)
    lines = lines[lines["stat"].isin(STATS)]
    cons = consensus(lines)
    games = nba_data.player_game_logs(season)
    feats = gf.build(season, prior)
    chosen = json.load(open(os.path.join(ROOT, "analysis", "game_fix.json")))["chosen"]
    names = games.drop_duplicates("PLAYER_ID", keep="last").set_index("PLAYER_ID")["PLAYER_NAME"]
    feats["key"] = feats["id"].map(names).map(rl.key)
    cons["key"] = cons["player"].map(rl.key)
    news = news_games(season, cons, games, abbr)
    spreads = pd.read_csv(spreads_path) if spreads_path and os.path.exists(spreads_path) else pd.DataFrame(columns=["event_id", "home_spread", "home", "away", "game_date"])
    # Spread by game: the median home spread; matched on date + teams (event ids can differ between endpoints).
    sp = spreads.groupby(["game_date", "home", "away"])["home_spread"].median().to_dict()
    out = []
    for stat in STATS:
        mean, var = gf.means_vars(feats, stat, chosen[stat])
        f = feats.assign(mean=mean, var=var)[["date", "key", "mean", "var", "min_mean", f"{stat}_y"]].rename(columns={f"{stat}_y": "y"})
        c = cons[cons["stat"] == stat].merge(f, left_on=["game_date", "key"], right_on=["date", "key"])
        c = c[~np.isclose(c["line"], np.round(c["line"]))].copy()            # half-point lines (no pushes)
        c["p_model"] = 1 - sst.norm.cdf(c["line"], c["mean"], np.sqrt(c["var"] * VAR_MULT))
        io, iu = 1 / c["med_over"], 1 / c["med_under"]
        c["p_market"] = io / (io + iu)
        c["p"] = expit(logit(c["p_market"]) + BLEND_W[stat] * (logit(c["p_model"]) - logit(c["p_market"])))
        out.append(c)
    d = pd.concat(out, ignore_index=True)
    d["over_won"] = d["y"] > d["line"]
    d["spread"] = [sp.get((r.game_date, r.home, r.away), np.nan) for r in d.itertuples()]
    d["news"] = d["event_id"].isin(news)
    d["gap"] = (d["p_model"] - d["p_market"]).abs()
    d["role"] = d["min_mean"] < ROTATION_MPG
    return d


def select(d, drop=(), price="best"):
    """Apply the rules (minus any in `drop`) and return the bets with their profit."""
    po = d["p"].to_numpy()
    dec_o = d[f"{price}_over"].to_numpy() if price == "best" else d["med_over"].to_numpy()
    dec_u = d[f"{price}_under"].to_numpy() if price == "best" else d["med_under"].to_numpy()
    ev_o, ev_u = po * (dec_o - 1) - (1 - po), (1 - po) * (dec_u - 1) - po
    over = ev_o >= ev_u
    ev = np.where(over, ev_o, ev_u)
    keep = ev >= (MIN_EV if "R2" not in drop else 0.0)
    if "R3" not in drop:
        keep &= ~d["news"].to_numpy()
    if "R4" not in drop:
        keep &= d["gap"].to_numpy() <= MAX_GAP
    if "R5" not in drop:
        keep &= ~(over & (np.abs(d["spread"].to_numpy()) >= BLOWOUT_SPREAD))
    won = np.where(over, d["over_won"], ~d["over_won"])
    dec = np.where(over, dec_o, dec_u)
    b = d.assign(side=np.where(over, "over", "under"), ev=ev, dec=dec, profit=np.where(won, dec - 1, -1.0))[keep]
    return b


def summary(b, boot=2000, seed=7):
    if not len(b):
        return {"bets": 0}
    days = b["game_date"].unique()
    by_day = {k: g["profit"].to_numpy() for k, g in b.groupby("game_date")}
    rng = np.random.default_rng(seed)
    sims = [np.concatenate([by_day[x] for x in rng.choice(days, len(days))]).mean() for _ in range(boot)]
    return {"bets": int(len(b)), "roi": float(b["profit"].mean()), "ci95": [float(np.percentile(sims, 2.5)), float(np.percentile(sims, 97.5))],
            "hit": float((b["profit"] > 0).mean()), "break_even": float((1 / b["dec"]).mean()), "days": int(len(days))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("season")
    ap.add_argument("--lines", default=os.path.join(ROOT, "data", "lines", "history.csv"))
    ap.add_argument("--spreads", default=os.path.join(ROOT, "data", "lines", "spreads.csv"))
    a = ap.parse_args()
    prior = nba_data.previous_season(a.season)
    d = evaluate(a.season, prior, a.lines, a.spreads)
    bets = select(d)
    res = {"rules": "docs/prereg-real-lines-rules.md", "season": a.season, "offers": int(len(d)),
           "games_with_news": int(d.loc[d["news"], "event_id"].nunique()), "games": int(d["event_id"].nunique()),
           "spread_known": float(d["spread"].notna().mean()),
           "all_rules": summary(bets),
           "at_median_prices": summary(select(d, price="median")),
           "without": {r: summary(select(d, drop=(r,))) for r in ("R2", "R3", "R4", "R5")},
           "by_side": {s: summary(bets[bets["side"] == s]) for s in ("over", "under")},
           "by_role": {"role players": summary(bets[bets["role"]]), "starters": summary(bets[~bets["role"]])},
           "by_stat": {s: summary(bets[bets["stat"] == s]) for s in STATS}}
    with open(os.path.join(ROOT, "analysis", f"real_lines_rules_{a.season}.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, indent=1)
    def line(name, s):
        if not s.get("bets"):
            return f"  {name:22} 0 bets"
        return f"  {name:22} {s['bets']:5} bets  ROI {s['roi']:+.3f}  95% [{s['ci95'][0]:+.3f}, {s['ci95'][1]:+.3f}]  won {s['hit']:.3f} (break-even {s['break_even']:.3f})"
    print(f"{a.season}: {res['games']} games, {res['offers']} offers; fresh injury news in {res['games_with_news']} games; spread known {res['spread_known']:.0%}")
    print(line("ALL RULES", res["all_rules"]))
    print(line("same bets, median price", res["at_median_prices"]))
    for r, s in res["without"].items():
        print(line(f"without {r}", s))
    for k, s in {**res["by_side"], **res["by_role"], **res["by_stat"]}.items():
        print(line(k, s))


if __name__ == "__main__":
    main()
