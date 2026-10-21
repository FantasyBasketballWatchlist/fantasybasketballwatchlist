"""BPV and NBA team win totals (rules: docs/prereg-win-totals.md).

    python -m analysis.win_totals            (writes analysis/win_totals.json)
"""
import datetime as dt
import json
import os
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("NBA_OFFLINE", "1")

from analysis import backtest as bt   # noqa: E402
import bpv   # noqa: E402
import nba_data   # noqa: E402
import ratings   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINES = os.path.join(ROOT, "data", "win_totals", "preseason_lines.csv")
OUT = os.path.join(ROOT, "analysis", "win_totals.json")
DESIGN = ["2020-21", "2021-22", "2022-23"]
TEST = ["2023-24", "2024-25", "2025-26"]
EDGE = 2.0
PRICE = 1 + 100 / 110          # -110


def team_ids():
    from nba_api.stats.static import teams
    t = teams.get_teams()
    by_name = {x["full_name"]: x["id"] for x in t}
    by_name["LA Clippers"] = by_name.get("Los Angeles Clippers")
    return by_name


def season_strength(pg, tg, hist, league_p, league_q, t):
    """S (standardized), raw value above replacement per team, games in the season, last season's win share."""
    prev = bt.SEASONS[bt.SEASONS.index(t) - 1]
    try:
        curve = bt.age_curve_before(pg, t)
    except ValueError:                               # 2020-21: no earlier seasons to fit the age curve on
        curve = None
    df, R = bt.preseason_frame(pg, hist, t, ratings.AVAILABILITY_DECAY, ratings.AVAILABILITY_K, league_p, league_q,
                               age_curve=curve)
    # Per-game value with age, back out from "BPV + age" (= p x prod + (1 - p) x q x R).
    col = "BPV + age" if curve is not None else "BPV (replacement-level)"
    prod = (df[col] - (1 - df.p_hat) * league_q * R) / df.p_hat
    games = int(tg[t].groupby("TEAM_ID").size().median())
    value = (prod - R).clip(lower=0) * df.p_hat * games
    # Team: last team last season, unless he played for another team in the first 21 days of this one.
    last_team = pg[prev].sort_values("GAME_DATE").groupby("PLAYER_ID").TEAM_ID.last()
    g = pg[t].sort_values("GAME_DATE")
    start = dt.date.fromisoformat(g.GAME_DATE.min())
    early = g[g.GAME_DATE <= (start + dt.timedelta(days=21)).isoformat()].groupby("PLAYER_ID").TEAM_ID.first()
    team = last_team.reindex(value.index)
    team.update(early.reindex(value.index).dropna())
    s = value.groupby(team).sum()
    prev_share = tg[prev].groupby("TEAM_ID").WL.apply(lambda w: (w == "W").mean())
    actual = tg[t].groupby("TEAM_ID").WL.apply(lambda w: (w == "W").sum())
    out = pd.DataFrame({"raw": s, "prev_share": prev_share.reindex(s.index), "actual": actual.reindex(s.index)})
    out["S"] = (out.raw - out.raw.mean()) / out.raw.std()
    out["games"] = games
    out["season"] = t
    return out.dropna()


def main():
    pg, tg = bt.load()
    draft = nba_data.draft_history()
    hist = bpv.availability_history(bt.SEASONS, pg, tg, draft)
    league_p, league_q = bpv.league_availability(hist)
    frames = [season_strength(pg, tg, hist, league_p, league_q, t) for t in DESIGN + TEST]
    d = pd.concat(frames)
    d.index.name = "TEAM_ID"
    d = d.reset_index()
    lines = pd.read_csv(LINES)
    lines["TEAM_ID"] = lines["team"].map(team_ids())
    d = d.merge(lines[["season", "TEAM_ID", "team", "line"]], on=["season", "TEAM_ID"])
    assert len(d) == 180, len(d)

    # Fit on the design seasons: wins per game = a + b S + c (prev share - 0.5).
    des = d[d.season.isin(DESIGN)]
    X = np.column_stack([np.ones(len(des)), des.S, des.prev_share - 0.5])
    y = des.actual / des.games
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    d["proj"] = (coef[0] + coef[1] * d.S + coef[2] * (d.prev_share - 0.5)) * d.games
    # Blend weight (secondary): actual - line = w (proj - line), fitted on design.
    dd = d[d.season.isin(DESIGN)]
    w = float(((dd.proj - dd.line) * (dd.actual - dd.line)).sum() / ((dd.proj - dd.line) ** 2).sum())

    def bets(x, edge):
        gap = x.proj - x.line
        b = x[gap.abs() >= edge].copy()
        b["side"] = np.where(b.proj > b.line, "over", "under")
        b["won"] = np.where(b.side == "over", b.actual > b.line, b.actual < b.line)
        b["profit"] = np.where(b.won, PRICE - 1, -1.0)
        return b

    test = d[d.season.isin(TEST)]
    res = {"rules": "docs/prereg-win-totals.md", "coef": {"a": float(coef[0]), "b_S": float(coef[1]), "c_prev": float(coef[2])},
           "design_fit": {"mae_proj": float((des.proj - des.actual).abs().mean()) if "proj" in des else None},
           "test": {}, "blend_w_design": w}
    des = d[d.season.isin(DESIGN)]
    res["design_fit"] = {"mae_proj": float((des.proj - des.actual).abs().mean()), "mae_line": float((des.line - des.actual).abs().mean()),
                         "bets": _summ(bets(des, EDGE))}
    for t in TEST:
        x = d[d.season == t]
        res["test"][t] = {"mae_proj": float((x.proj - x.actual).abs().mean()), "mae_line": float((x.line - x.actual).abs().mean()),
                          "mae_blend": float((x.line + w * (x.proj - x.line) - x.actual).abs().mean()), "bets": _summ(bets(x, EDGE)),
                          "bets_edge3": _summ(bets(x, 3.0))}
    allb = bets(test, EDGE)
    res["test_all"] = {"bets": _summ(allb), "bets_edge3": _summ(bets(test, 3.0)),
                       "mae_proj": float((test.proj - test.actual).abs().mean()), "mae_line": float((test.line - test.actual).abs().mean()),
                       "mae_blend": float((test.line + w * (test.proj - test.line) - test.actual).abs().mean())}
    seasons_above = sum(res["test"][t]["bets"]["hit"] is not None and res["test"][t]["bets"]["hit"] > 0.524 for t in TEST)
    res["passes"] = bool(res["test_all"]["bets"]["hit"] is not None and res["test_all"]["bets"]["hit"] >= 0.55 and seasons_above >= 2)
    res["test_bets"] = allb[["season", "team", "line", "proj", "actual", "side", "won"]].round(1).to_dict(orient="records")
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=float)
    print(json.dumps({k: v for k, v in res.items() if k != "test_bets"}, indent=1, default=float))


def _summ(b):
    if not len(b):
        return {"bets": 0, "hit": None, "roi": None}
    return {"bets": int(len(b)), "hit": float(b.won.mean()), "roi": float(b.profit.mean()),
            "overs": int((b.side == "over").sum()), "unders": int((b.side == "under").sum())}


if __name__ == "__main__":
    main()
