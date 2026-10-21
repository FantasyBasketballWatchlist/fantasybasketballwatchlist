import datetime
import functools
import hashlib
import json
import math
import os
import threading

from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException

import nba_data
import ratings
from analysis import accuracy_tracker

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True    # pick up template edits without a restart
# Static files are fingerprinted (?v=<hash>, below), so browsers can keep them for a year.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 365 * 24 * 3600
ROOT = os.path.dirname(os.path.abspath(__file__))
TRACKING_SUMMARY = os.path.join(ROOT, "data", "tracking", "summary.json")
_static_hashes = {}


@app.url_defaults
def _fingerprint_static(endpoint, values):
    if endpoint == "static" and "filename" in values:
        name = values["filename"]
        if name not in _static_hashes:
            try:
                with open(os.path.join(app.static_folder, name), "rb") as f:
                    _static_hashes[name] = hashlib.md5(f.read()).hexdigest()[:10]
            except OSError:
                _static_hashes[name] = None
        if _static_hashes[name]:
            values["v"] = _static_hashes[name]


_responses, _responses_lock = {}, threading.Lock()


def cached_json(view):
    """Reuse a route's JSON until the ratings are rebuilt (same URL, same answer)."""
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        ratings.get()                                   # rebuilds first if the ratings are stale
        key = (request.path, request.query_string, ratings.version())
        with _responses_lock:
            hit = _responses.get(key)
        if hit is not None:
            body, status = hit
            return app.response_class(body, status=status, mimetype="application/json")
        response = app.make_response(view(*args, **kwargs))
        if response.status_code in (200, 400, 404):
            with _responses_lock:
                if len(_responses) > 2000 or any(k[2] != key[2] for k in list(_responses)[:1]):
                    _responses.clear()                  # new ratings (or too many entries): start over
                _responses[key] = (response.get_data(), response.status_code)
        return response
    return wrapper


def _data_version():
    """Stamp written by refresh.py whenever it publishes new data (None when running locally)."""
    try:
        with open(os.path.join(nba_data.CACHE_DIR, "VERSION"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return None

WAIVER_LIST_SIZE = 15


def _clean(value):
    """Make pandas/numpy values JSON-safe (NaN -> None)."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def _records(df):
    return [_clean(r) for r in df.to_dict(orient="records")]


def _find(players, player_id=None, name=None):
    if player_id is not None:
        match = players[players["id"] == player_id]
    else:
        match = players[players["name"].map(ratings.normalize_name) == ratings.normalize_name(name or "")]
    return None if match.empty else match.iloc[0]


# Only what the pages display goes out: the model's internals (method notes, weights, baselines, availability
# components) stay on the server.
PUBLIC_META = ["mode", "season", "target_season", "league_teams", "roster_size", "replacement_level", "playoff_games_range"]
PUBLIC_PLAYER = ["id", "name", "team", "rank", "games", "bpv", "production", "availability", "season_fpts", "recent_fpts",
                 "value_over_replacement", "range_low", "range_high", "games_missed", "playoff_games", "playoff_fpts",
                 "week_games", "week_fpts", "espn_fpg", "espn_games", "heat_check_index", "report_status", "report_reason",
                 "play_probability", "injury_note", "rookie", "per_game", "joke_note"]


def _meta(meta):
    return {k: meta.get(k) for k in PUBLIC_META}


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/trade-analyzer")
def trade_analyzer():
    return render_template("trade-analyzer.html")


@app.route("/waiver-wires")
def waiver_wires():
    return render_template("waiver-wires.html")


@app.route("/trade-analyzer.html")
@app.route("/waiver-wires.html")
def old_page_urls():
    return redirect(request.path[:-len(".html")], code=301)


@app.route("/draft")
def draft_tracker():
    return render_template("draft.html")


@app.route("/league")
def league():
    return render_template("league.html")


@app.route("/leagues")
def your_leagues():
    return render_template("leagues.html")


@app.route("/injuries")
def injuries():
    return render_template("injuries.html")


@app.route("/betting")
def betting():
    return render_template("betting.html")


@app.route("/games")
def games():
    return redirect("/betting", code=301)                # the Games page became the Betting tab


# ---------- search engines and icons ----------
SITE_URL = "https://hoopothesis.cc"
PAGES = ["/", "/draft", "/league", "/leagues", "/injuries", "/betting", "/trade-analyzer", "/waiver-wires"]


@app.route("/hoopothesis-espn.user.js")
def espn_userscript():
    """The Tampermonkey script for live ESPN draft picks. Served from the root with no caching, so Tampermonkey installs
    it (the .user.js ending) and its update checks always see the newest version."""
    res = send_from_directory(app.static_folder, "hoopothesis-espn.user.js", max_age=0)
    res.headers["Content-Type"] = "text/javascript; charset=utf-8"
    return res


@app.route("/robots.txt")
def robots():
    # /api/ stays crawlable: search engines need it to render the pages. API responses are noindex instead.
    return Response(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n", mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap():
    today = datetime.date.today().isoformat()     # rankings are rebuilt every day
    urls = "".join(f"<url><loc>{SITE_URL}{p}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq>"
                   f"<priority>{'1.0' if p == '/' else '0.8'}</priority></url>" for p in PAGES)
    return Response('<?xml version="1.0" encoding="UTF-8"?>'
                    f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>', mimetype="application/xml")


@app.route("/site.webmanifest")
def manifest():
    return jsonify({
        "name": "Hoopothesis", "short_name": "Hoopothesis", "start_url": "/", "display": "standalone",
        "description": "Data-driven fantasy basketball rankings and projections.",
        "background_color": "#0a0f1c", "theme_color": "#0a0f1c",
        "icons": [{"src": "/static/icon-192.png", "sizes": "192x192", "type": "image/png"},
                  {"src": "/static/icon-512.png", "sizes": "512x512", "type": "image/png"},
                  {"src": "/static/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    })


@app.route("/favicon.ico")
@app.route("/apple-touch-icon.png")
def root_icons():
    # Browsers and iOS ask for these at the site root.
    return send_from_directory(app.static_folder, request.path.lstrip("/"), max_age=7 * 24 * 3600)


@app.after_request
def api_noindex(response):
    if request.path.startswith("/api/"):
        response.headers["X-Robots-Tag"] = "noindex"
    return response


@app.route("/api/meta")
@cached_json
def get_meta():
    _, meta = ratings.get()
    return jsonify(_clean({**_meta(meta), "data_version": _data_version()}))


ACCURACY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "accuracy.json")


@app.route("/api/accuracy")
def get_accuracy():
    """Saved snapshots scored against actual results (rescored automatically every few hours),
    plus the in-season checks refresh.py runs (data/tracking/summary.json)."""
    try:
        accuracy_tracker.refresh()
    except Exception:
        app.logger.exception("accuracy scoring failed")
    out = {"updated": None, "snapshots": []}
    if os.path.exists(ACCURACY_PATH):
        with open(ACCURACY_PATH, encoding="utf-8") as f:
            out = json.load(f)
    if os.path.exists(TRACKING_SUMMARY):
        with open(TRACKING_SUMMARY, encoding="utf-8") as f:
            out["live_checks"] = json.load(f)
    return jsonify(out)


@app.route("/api/players")
@cached_json
def get_players():
    """Search list: every player with a rating."""
    players, _ = ratings.get()
    return jsonify(_records(players[["id", "name", "team", "rank"]]))


@app.route("/api/player")
@cached_json
def get_player():
    players, meta = ratings.get()
    player_id = request.args.get("id", type=int)
    player = _find(players, player_id, request.args.get("name"))
    if player is None:
        return jsonify({"error": "Player not found"}), 404
    player = player.to_dict()
    return jsonify({"player": _clean({k: player.get(k) for k in PUBLIC_PLAYER}), "meta": _clean(_meta(meta))})


@app.route("/api/rankings")
@cached_json
def get_rankings():
    players, meta = ratings.get()
    limit = request.args.get("limit", default=200, type=int)
    cols = ["rank", "id", "name", "team", "games", "production", "season_fpts", "recent_fpts", "range_low", "range_high", "availability", "bpv",
            "value_over_replacement", "heat_check_index", "playoff_games", "playoff_fpts", "week_games", "week_fpts", "injury_note", "report_status", "play_probability", "rookie",
            "report_reason", "minutes_change_fpts", "efficiency_change_fpts"]
    return jsonify({"players": _records(players[cols].head(limit)), "meta": _meta(meta)})


@app.route("/api/injuries")
@cached_json
def get_injuries():
    """The latest official injury report, joined to BPV (see ratings.injury_list)."""
    players, meta = ratings.get()
    return jsonify(_clean({**ratings.injury_list(players, meta), "meta": _meta(meta)}))


@app.route("/api/games")
@cached_json
def get_games():
    """Single-game projections for the next game day (game_projections.today): per player, the mean and spread of each
    stat if he plays, his chance of playing, and his season average."""
    import game_projections
    players, meta = ratings.get()
    out = game_projections.today(players, meta)
    keep = [r for r in out["players"] if r["minutes"] >= 8]
    for r in keep:
        for st in r["stats"].values():
            for k in ("mean", "var", "q10", "q50", "q90"):
                st[k] = round(float(st[k]), 3)
    return jsonify(_clean({"day": out["day"], "games": out["games"], "players": keep, "labels": out.get("labels"),
                           "stats": out.get("stats"), "meta": _meta(meta)}))


@app.route("/api/betting-status")
def get_betting_status():
    """The corner search's latest results (data/tracking/corners_*.json, written by refresh.py on the PC)."""
    out = {}
    for src in ("history", "live", "morning"):
        path = os.path.join(ROOT, "data", "tracking", f"corners_{src}.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            out[src] = {k: d.get(k) for k in ("updated", "status", "game_days", "bets", "mean_clv", "discover_bets", "confirm_bets",
                                              "corners_tested", "discovered", "metric", "baseline")}
            out[src]["confirmed"] = [{k: c.get(k) for k in ("corner", "bets", "mean", "p", "confirm")} for c in d.get("confirmed", [])]
    return jsonify(out)


@app.route("/api/positions")
@cached_json
def get_positions():
    """player id -> ESPN position eligibility ("PG/SG"), for players ESPN lists."""
    players, meta = ratings.get()
    season = meta.get("target_season") or meta["season"]
    try:
        espn = nba_data.espn_positions(season)
    except Exception:
        app.logger.exception("ESPN positions unavailable")
        return jsonify({"positions": {}, "source": None})
    by_key = dict(zip(espn["PLAYER_NAME"].map(ratings._espn_key), espn["POSITIONS"]))
    positions = {int(pid): by_key[k] for pid, k in zip(players["id"], players["name"].map(ratings._espn_key)) if k in by_key}
    return jsonify({"positions": positions, "source": f"ESPN, {season}"})


@app.route("/api/trade")
@cached_json
def analyze_trade():
    """Compare two sides of a trade by value over replacement.

    Summing raw BPV favors whichever side gets more players, but a roster spot
    isn't free: the side receiving fewer players fills the open spots with free
    agents worth the replacement level. Comparing value over replacement
    (BPV - replacement) accounts for that.
    """
    players, meta = ratings.get()
    sides = {}
    for side in ("give", "get"):
        ids = [int(x) for x in request.args.get(side, "").split(",") if x.strip().isdigit()]
        rows = players[players["id"].isin(ids)]
        sides[side] = {
            "players": _records(rows[["id", "name", "team", "rank", "bpv", "value_over_replacement",
                                      "production", "availability", "injury_note"]]),
            "total_bpv": float(rows["bpv"].sum()),
            "total_value_over_replacement": float(rows["value_over_replacement"].sum()),
        }
    if not sides["give"]["players"] or not sides["get"]["players"]:
        return jsonify({"error": "Add at least one player to each side."}), 400
    difference = sides["get"]["total_value_over_replacement"] - sides["give"]["total_value_over_replacement"]
    return jsonify({**sides, "difference": difference, "meta": _meta(meta)})


@app.route("/api/waiver")
@cached_json
def waiver_signals():
    """Players whose last 5 games differ from their season, split by why.

    Minutes changes tend to stick; per-minute (shooting) swings mostly fade.
    With a league (?mine=ids of your team&others=ids on the other teams): minutes risers are free agents only,
    hot shooters and falling minutes are your own players (sell high, drop), cold shooters are on other teams (buy
    low), and the answer adds your team's players and the best free agents.
    """
    players, meta = ratings.get()
    threshold = request.args.get("threshold", default=4.0, type=float)
    ids = lambda key: {int(x) for x in request.args.get(key, "").split(",") if x.strip().isdigit()}
    mine, others = ids("mine"), ids("others")
    league = bool(mine or others)
    df = players[(players["games"] >= ratings.ROLE_MIN_GAMES)].copy()
    cols = ["id", "name", "team", "games", "season_fpts", "recent_fpts", "recent_minutes",
            "minutes_change_fpts", "efficiency_change_fpts", "bpv"]
    mc, ec = df["minutes_change_fpts"], df["efficiency_change_fpts"]
    free, own, theirs = ~df["id"].isin(mine | others), df["id"].isin(mine), df["id"].isin(others)
    pick = lambda mask, group: mask & group if league else mask
    lists = {
        "rising_minutes": df[pick(mc >= threshold, free)].sort_values("minutes_change_fpts", ascending=False),
        "hot_shooting": df[pick((ec >= threshold) & (mc.abs() < threshold / 2), own)].sort_values("efficiency_change_fpts", ascending=False),
        "cold_shooting": df[pick((ec <= -threshold) & (mc.abs() < threshold / 2), theirs)].sort_values("efficiency_change_fpts"),
        "falling_minutes": df[pick(mc <= -threshold, own)].sort_values("minutes_change_fpts"),
    }
    out = {**{k: _records(v[cols].head(WAIVER_LIST_SIZE)) for k, v in lists.items()},
           "threshold": threshold, "league": league, "meta": _meta(meta)}
    if league:
        team_cols = cols + ["rank", "production", "availability", "injury_note", "report_status", "report_reason",
                            "week_games", "week_fpts"]
        out["team"] = _records(players[players["id"].isin(mine)][team_cols])
        fa = players[~players["id"].isin(mine | others)].sort_values("bpv", ascending=False)
        out["free_agents"] = _records(fa[team_cols].head(WAIVER_LIST_SIZE))
    return jsonify(out)


@app.errorhandler(Exception)
def handle_error(e):
    if isinstance(e, HTTPException):
        return e
    app.logger.exception("Request failed")
    return jsonify({"error": "Could not load NBA data right now. Try again in a minute."}), 500


if __name__ == "__main__":
    # Debug mode exposes an interactive debugger; only enable it on your own machine.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1",
            host=os.environ.get("HOST", "127.0.0.1"),
            port=int(os.environ.get("PORT", 8080)))
