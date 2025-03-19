import os
import unicodedata
import redis
import json
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, PlayerGameLogs
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players
from urllib.parse import urlparse
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type
import requests
from requests.exceptions import RequestException
from celery import Celery
import logging

# Configure logging for better debugging
logging.basicConfig(level=logging.INFO)

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

# Celery configuration
app.config['CELERY_BROKER_URL'] = redis_url  # Redis broker URL
app.config['CELERY_RESULT_BACKEND'] = redis_url  # Redis result backend

# Ensure Celery handles rediss URLs properly
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Static list of top 10 players (you can customize this list)
top_players = [
    "LeBron James",
    "Giannis Antetokounmpo",
    "Luka Dončić",
    "Tyrese Haliburton",  # Fixed spelling from "Halliburton"
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
    data = redis_client.get(key)
    if data:
        try:
            return json.loads(data)  # Parse JSON string back to Python object
        except json.JSONDecodeError:
            return data
    return None

def set_to_cache(key, value, expiration=3600):
    if isinstance(value, (dict, list)):
        value = json.dumps(value)  # Convert Python object to JSON string
    redis_client.setex(key, expiration, value)

# Modified the retry decorator for blocking web servers like gunicorn
def fetch_nba_data(request_function, *args, **kwargs):
    """
    A non-blocking version of the NBA API request function.
    Attempts the request once and returns the result or raises the exception.
    """
    try:
        return request_function(*args, **kwargs)
    except Exception as e:
        logging.error(f"Error fetching NBA data: {str(e)}")
        raise

# Celery Task for retrying NBA API requests
@celery.task(bind=True, max_retries=3, default_retry_delay=2)
def retry_nba_api(self, request_function_name, *args, **kwargs):
    """
    A Celery task that can retry NBA API requests if they fail.
    """
    # Map function names to actual functions
    function_map = {
        'PlayerCareerStats': PlayerCareerStats,
        'PlayerGameLogs': PlayerGameLogs,
        'ScoreBoard': ScoreBoard
    }
    
    request_function = function_map.get(request_function_name)
    if not request_function:
        raise ValueError(f"Unknown function: {request_function_name}")
        
    try:
        return request_function(*args, **kwargs).get_dict()
    except Exception as e:
        # Retry up to 3 times
        if self.request.retries < 3:
            raise self.retry(exc=e)
        raise

# Celery Task Example
@celery.task
def fetch_player_stats_in_background(player_name):
    player = find_player_by_name(player_name)
    if player:
        try:
            career = PlayerCareerStats(player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']
            if rows:
                stats = [dict(zip(headers, row)) for row in rows]
                set_to_cache(f"player_stats:{player_name.lower()}", stats)
        except Exception as e:
            logging.error(f"Background task error for {player_name}: {str(e)}")
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
        # Fetch career stats using player ID - without blocking retries
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

        # Schedule background refresh as a separate task
        fetch_player_stats_in_background.delay(player_name)

        return jsonify(stats)

    except Exception as e:
        logging.error(f"Error fetching player stats for {player_name}: {str(e)}")
        return jsonify({"error": f"Error fetching player stats. Please try again later."}), 500

# Route for fetching today's NBA scoreboard
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    # Check cache first
    cache_key = "today_games"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)
        
    try:
        # Fetch today's NBA scoreboard data - without blocking retries
        games = fetch_nba_data(ScoreBoard)
        data = games.get_dict()

        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify({"message": "No live games available today."}), 200

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
            
        # Cache the results for 5 minutes (games update frequently)
        set_to_cache(cache_key, game_data, expiration=300)

        return jsonify(game_data)

    except Exception as e:
        logging.error(f"Error fetching today's games: {str(e)}")
        return jsonify({"error": f"Error fetching today's games. Please try again later."}), 500

# Route for fetching active players list (for frontend autocomplete)
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    # Check cache first
    cache_key = "active_players"
    cached_players = get_from_cache(cache_key)
    
    if cached_players:
        return jsonify(cached_players)
        
    try:
        # Fetch the full list of players (active and inactive)
        all_players = players.get_players()

        if not all_players:
            return jsonify({"error": "No players found."}), 500

        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        # Cache active players for 24 hours (doesn't change often)
        set_to_cache(cache_key, player_data, expiration=86400)

        return jsonify(player_data)

    except Exception as e:
        logging.error(f"Error fetching active players: {str(e)}")
        return jsonify({"error": f"Error fetching active players. Please try again later."}), 500

# Route for fetching last 5 games for a player
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Check cache first
    cache_key = f"last_5_games:{player_name.lower()}"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)

    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404

    try:
        # Fetch game logs without blocking retries
        game_logs = fetch_nba_data(PlayerGameLogs, player_id_nullable=player['id'], last_n_games_nullable=5)
        game_log_data = game_logs.get_dict()['resultSets'][0]
        
        headers = game_log_data['headers']
        rows = game_log_data['rowSet']
        
        if not rows:
            return jsonify({"message": "No recent games found for this player."}), 200
            
        last_5_games = []
        for row in rows:
            game_dict = dict(zip(headers, row))
            formatted_game = {
                "date": game_dict.get("GAME_DATE", "N/A"),
                "home_team": game_dict.get("HOME_TEAM_NAME", "N/A"),
                "away_team": game_dict.get("VISITOR_TEAM_NAME", "N/A"),
                "home_score": game_dict.get("HOME_TEAM_SCORE", "N/A"),
                "away_score": game_dict.get("VISITOR_TEAM_SCORE", "N/A"),
                "outcome": game_dict.get("WL", "N/A"),
            }
            last_5_games.append(formatted_game)
            
        # Cache the results for 6 hours
        set_to_cache(cache_key, last_5_games, expiration=21600)

        return jsonify(last_5_games)

    except Exception as e:
        logging.error(f"Error fetching last 5 games for {player_name}: {str(e)}")
        return jsonify({"error": f"Error fetching last 5 games. Please try again later."}), 500

# Route for fetching stats for the static top 10 players
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # Check cache first
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
        
    top_players_stats = []

    for player_name in top_players:
        player = find_player_by_name(player_name)

        if not player:
            continue  # If player not found, skip to the next one

        try:
            # Fetch career stats without blocking retries
            career = fetch_nba_data(PlayerCareerStats, player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']

            if not rows:
                continue

            # Look for current season stats - ensure this matches the current NBA season format
            current_season = '2024-25'
            current_season_stats = None
            
            for row in rows:
                if row[headers.index('SEASON_ID')] == current_season:
                    current_season_stats = dict(zip(headers, row))
                    break
                    
            # If no current season stats, use the most recent one
            if not current_season_stats and rows:
                current_season_stats = dict(zip(headers, rows[-1]))  # Last row is most recent

            if current_season_stats:
                # Filter to just show key stats
                simplified_stats = {
                    "season": current_season_stats.get("SEASON_ID"),
                    "team": current_season_stats.get("TEAM_ABBREVIATION"),
                    "games_played": current_season_stats.get("GP"),
                    "ppg": current_season_stats.get("PTS"),
                    "rpg": current_season_stats.get("REB"),
                    "apg": current_season_stats.get("AST"),
                    "fg_pct": current_season_stats.get("FG_PCT"),
                    "fg3_pct": current_season_stats.get("FG3_PCT")
                }
                
                top_players_stats.append({
                    "player_name": player_name,
                    "stats": simplified_stats
                })

        except Exception as e:
            logging.error(f"Error fetching stats for {player_name}: {str(e)}")
            continue  # Skip to the next player on error
            
    # Cache the top players stats for 12 hours
    if top_players_stats:  # Only cache if we have stats
        set_to_cache(cache_key, top_players_stats, expiration=43200)

    return jsonify(top_players_stats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  
    app.run(debug=False, host='0.0.0.0', port=port)  # Set debug=False for production