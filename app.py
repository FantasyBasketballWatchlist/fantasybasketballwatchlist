import os
import unicodedata
import redis
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, PlayerGameLogs
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import requests
from requests.exceptions import RequestException
from celery import Celery  # Import Celery

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Get the Redis URL from the environment variable (Heroku Redis URL)
redis_url = os.getenv("REDIS_URL")

# Check if the Redis URL was not found
if not redis_url:
    raise ValueError("REDIS_URL environment variable is not set. Make sure to add Heroku Redis add-on.")

# Parse the Redis URL
url = urlparse(redis_url)

# Initialize Redis client with SSL support
redis_client = redis.StrictRedis(
    host=url.hostname,
    port=url.port,
    password=url.password,
    ssl=True,  # Enable SSL connection for rediss://
    ssl_cert_reqs=None,  # Disable certificate verification (specific to Heroku Redis)
    db=0,
    decode_responses=True
)

# Static list of top 10 players (you can customize this list)
top_players = [
    "LeBron James",
    "Giannis Antetokounmpo",
    "Luka Dončić",
    "Tyrese Halliburton",
    "Cade Cunningham",
    "Nikola Jokić",
    "Shai Gilgeous-Alexander",
    "Anthony Davis",
    "Victor Wembanyama",
    "Jayson Tatum",
]

# Helper function to remove accents from characters
def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# Function to search and return player by name
def find_player_by_name(player_name):
    player_name_normalized = remove_accents(player_name.strip().lower())
    all_players = players.get_players()  # Correctly using the function from the `players` module
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == player_name_normalized:
            return player
    return None

# Cache helper functions for Redis
def get_from_cache(key):
    return redis_client.get(key)

def set_to_cache(key, value, expiration=3600):
    redis_client.setex(key, expiration, value)

# Retry logic using `tenacity`
@retry(
    stop=stop_after_attempt(3),  # Retry up to 3 attempts
    wait=wait_fixed(2),  # Wait 2 seconds between retries
    retry=retry_if_exception_type(RequestException)  # Retry only for request exceptions
)
def fetch_nba_data(request_function, *args, **kwargs):
    """
    A wrapper around the NBA API requests to retry in case of failure.
    This function will retry the request up to 3 times with a 2-second delay.
    """
    return request_function(*args, **kwargs)

# Celery configuration
app.config['CELERY_BROKER_URL'] = redis_url  # Redis broker URL
app.config['CELERY_RESULT_BACKEND'] = redis_url  # Redis result backend
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Celery Task Example
@celery.task
def fetch_player_stats_in_background(player_name):
    player = find_player_by_name(player_name)
    if player:
        career = fetch_nba_data(PlayerCareerStats, player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        if rows:
            stats = [dict(zip(headers, row)) for row in rows]
            set_to_cache(f"player_stats:{player_name.lower()}", stats)
    return "Player stats fetched in background"

# Homepage route
@app.route('/')
def home():
    return render_template('index.html')  # You can replace this with your homepage template

# Route for fetching career stats for a player by name (not ID)
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Try to get the stats from Redis cache first
    cache_key = f"player_stats:{player_name.lower()}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)  # Return cached data if available

    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404  # Error if player isn't found

    try:
        # Fetch career stats using player ID
        career = fetch_nba_data(PlayerCareerStats, player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        stats = [dict(zip(headers, row)) for row in rows]

        # Store the fetched stats in Redis for future use (with an expiration of 1 hour)
        set_to_cache(cache_key, stats, expiration=3600)

        # Trigger the background task for stats fetching
        fetch_player_stats_in_background.apply_async(args=[player_name])

        return jsonify(stats)

    except Exception as e:
        return jsonify({"error": f"Error fetching player stats: {str(e)}"}), 400  # Handle errors

@app.route('/trade-analyzer')
def trade_analyzer():
    return render_template('trade-analyzer.html')

# Route for fetching today's NBA scoreboard
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    try:
        # Fetch today's NBA scoreboard data
        games = fetch_nba_data(ScoreBoard)
        data = games.get_dict()

        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify({"error": "No live games available."}), 404

        # Format the game data
        game_data = []
        for game in game_list:
            game_data.append({
                "home_team": game['homeTeam']['teamName'],
                "away_team": game['awayTeam']['teamName'],
                "home_score": game['homeTeam']['score'],
                "away_score": game['awayTeam']['score'],
                "status": game['gameStatusText']
            })

        return jsonify(game_data)

    except Exception as e:
        return jsonify({"error": f"Error fetching today's games: {str(e)}"}), 400

# Route for fetching active players list (for frontend autocomplete)
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    try:
        # Fetch the full list of players (active and inactive)
        all_players = players.get_players()

        if not all_players:
            return jsonify({"error": "No players found."}), 500

        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]

        return jsonify(player_data)

    except Exception as e:
        return jsonify({"error": f"Error fetching active players: {str(e)}"}), 500

# Route for fetching last 5 games for a player
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404

    try:
        game_logs = PlayerGameLogs(player_id_nullable=player['id'], last_n_games_nullable=5)
        game_log_data = game_logs.player_game_logs.get_data()

        last_5_games = []
        for game in game_log_data:
            formatted_game = {
                "date": game.get("GAME_DATE", "N/A"),
                "home_team": game.get("HOME_TEAM_NAME", "N/A"),
                "away_team": game.get("VISITOR_TEAM_NAME", "N/A"),
                "home_score": game.get("HOME_TEAM_SCORE", "N/A"),
                "away_score": game.get("VISITOR_TEAM_SCORE", "N/A"),
                "outcome": game.get("WL", "N/A"),
            }
            last_5_games.append(formatted_game)

        return jsonify(last_5_games)

    except Exception as e:
        return jsonify({"error": f"Error fetching last 5 games: {str(e)}"}), 400

# Route for fetching stats for the static top 10 players
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    top_players_stats = []

    for player_name in top_players:
        player = find_player_by_name(player_name)

        if not player:
            continue  # If player not found, skip to the next one

        cache_key = f"player_stats_top:{player_name.lower()}"
        cached_stats = get_from_cache(cache_key)
        
        if cached_stats:
            top_players_stats.append({"player_name": player_name, "stats": cached_stats})
            continue  # Skip to the next player if stats are cached

        try:
            career = fetch_nba_data(PlayerCareerStats, player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']

            if not rows:
                continue

            stats_2024_25 = [
                dict(zip(headers, row)) for row in rows if row[headers.index('SEASON_ID')] == '2024-25'
            ]

            if stats_2024_25:
                season_stats = stats_2024_25[0]
                top_players_stats.append({
                    "player_name": player_name,
                    "stats": season_stats
                })

                # Cache the stats for future requests
                set_to_cache(cache_key, season_stats)

        except Exception as e:
            print(f"Error fetching stats for {player_name}: {str(e)}")

    return jsonify(top_players_stats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  
    app.run(debug=True, host='0.0.0.0', port=port)
