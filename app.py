import datetime
import json
import math
import os

from flask import Flask, Response, jsonify, redirect, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException

import nba_data
import ratings
from analysis import accuracy_tracker

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True    # pick up template edits without a restart

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


def _meta(meta):
    return {k: v for k, v in meta.items() if k != "rookie_baselines"}


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


# ---------- search engines and icons ----------
SITE_URL = "https://hoopothesis.cc"
PAGES = ["/", "/draft", "/league", "/trade-analyzer", "/waiver-wires"]


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
def get_meta():
    _, meta = ratings.get()
    return jsonify(_clean(meta))


ACCURACY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "accuracy.json")


@app.route("/api/accuracy")
def get_accuracy():
    """Saved snapshots scored against actual results (rescored automatically every few hours)."""
    try:
        accuracy_tracker.refresh()
    except Exception:
        app.logger.exception("accuracy scoring failed")
    if not os.path.exists(ACCURACY_PATH):
        return jsonify({"updated": None, "snapshots": []})
    with open(ACCURACY_PATH, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.route("/api/players")
def get_players():
    """Search list: every player with a rating."""
    players, _ = ratings.get()
    return jsonify(_records(players[["id", "name", "team", "rank"]]))


@app.route("/api/player")
def get_player():
    players, meta = ratings.get()
    player_id = request.args.get("id", type=int)
    player = _find(players, player_id, request.args.get("name"))
    if player is None:
        return jsonify({"error": "Player not found"}), 404
    return jsonify({"player": _clean(player.to_dict()), "meta": _meta(meta)})


@app.route("/api/rankings")
def get_rankings():
    players, meta = ratings.get()
    limit = request.args.get("limit", default=200, type=int)
    cols = ["rank", "id", "name", "team", "games", "production", "season_fpts", "recent_fpts", "range_low", "range_high", "availability", "bpv",
            "value_over_replacement", "heat_check_index", "playoff_games", "playoff_fpts", "week_games", "week_fpts", "production_note", "injury_note", "report_status", "play_probability", "rookie"]
    return jsonify({"players": _records(players[cols].head(limit)), "meta": _meta(meta)})


@app.route("/api/positions")
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
def waiver_signals():
    """Players whose last 5 games differ from their season, split by why.

    Minutes changes tend to stick; per-minute (shooting) swings mostly fade.
    """
    players, meta = ratings.get()
    threshold = request.args.get("threshold", default=4.0, type=float)
    df = players[(players["games"] >= ratings.ROLE_MIN_GAMES)].copy()
    cols = ["id", "name", "team", "games", "season_fpts", "recent_fpts", "recent_minutes",
            "minutes_change_fpts", "efficiency_change_fpts", "bpv", "production_note"]
    mc, ec = df["minutes_change_fpts"], df["efficiency_change_fpts"]
    lists = {
        "rising_minutes": df[mc >= threshold].sort_values("minutes_change_fpts", ascending=False),
        "hot_shooting": df[(ec >= threshold) & (mc.abs() < threshold / 2)].sort_values("efficiency_change_fpts", ascending=False),
        "cold_shooting": df[(ec <= -threshold) & (mc.abs() < threshold / 2)].sort_values("efficiency_change_fpts"),
        "falling_minutes": df[mc <= -threshold].sort_values("minutes_change_fpts"),
    }
    return jsonify({**{k: _records(v[cols].head(WAIVER_LIST_SIZE)) for k, v in lists.items()},
                    "threshold": threshold, "meta": _meta(meta)})


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
