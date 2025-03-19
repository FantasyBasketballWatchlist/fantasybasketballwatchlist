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
import requests
from requests.exceptions import RequestException, Timeout
from celery import Celery
import logging
import ssl
import time

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

# Set proper SSL configuration for Redis
if url.scheme == 'rediss':
    # Fix for the Redis SSL configuration error
    redis_client = redis.StrictRedis(
        host=url.hostname,
        port=url.port,
        password=url.password,
        ssl=True,
        ssl_cert_reqs=ssl.CERT_NONE,  # Explicitly set SSL cert requirements
        db=0,
        decode_responses=True
    )
else:
    # Non-SSL Redis connection
    redis_client = redis.StrictRedis(
        host=url.hostname,
        port=url.port,
        password=url.password,
        ssl=False,
        db=0,
        decode_responses=True
    )

# Celery configuration with proper SSL settings
app.config['CELERY_BROKER_URL'] = redis_url
app.config['CELERY_RESULT_BACKEND'] = redis_url

# Ensure Celery handles rediss URLs properly
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Configure Celery to handle SSL properly for Redis
if url.scheme == 'rediss':
    celery.conf.broker_transport_options = {
        'ssl_cert_reqs': ssl.CERT_NONE
    }
    celery.conf.redis_backend_transport_options = {
        'ssl_cert_reqs': ssl.CERT_NONE
    }

# Static list of top 10 players (you can customize this list)
top_players = [
    "LeBron James",
    "Giannis Antetokounmpo",
    "Luka Dončić",
    "Tyrese Haliburton",
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
    all_players = players.get_players()
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == player_name_normalized:
            return player
    return None

# Cache helper functions for Redis
def get_from_cache(key):
    try:
        data = redis_client.get(key)
        if data:
            try:
                return json.loads(data)  # Parse JSON string back to Python object
            except json.JSONDecodeError:
                return data
        return None
    except Exception as e:
        logging.error(f"Redis cache get error: {str(e)}")
        return None

def set_to_cache(key, value, expiration=3600):
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)  # Convert Python object to JSON string
        redis_client.setex(key, expiration, value)
        return True
    except Exception as e:
        logging.error(f"Redis cache set error: {str(e)}")
        return False

# Safe NBA data fetching function with timeout handling
def fetch_nba_data(endpoint_class, timeout=10, **kwargs):
    """
    A safer version of the NBA API request function with better error handling and timeout.
    """
    try:
        # Set a shorter timeout to avoid Heroku H12 errors (30s limit)
        kwargs['timeout'] = timeout
        endpoint = endpoint_class(**kwargs)
        return endpoint
    except Timeout:
        logging.error(f"Timeout error fetching NBA data with {endpoint_class.__name__}")
        raise
    except Exception as e:
        logging.error(f"Error initializing NBA endpoint {endpoint_class.__name__}: {str(e)}")
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
    
    # Add timeout to kwargs if not present
    if 'timeout' not in kwargs:
        kwargs['timeout'] = 10
        
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
            career = PlayerCareerStats(player_id=player['id'], timeout=10)
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
        # Fetch career stats using player ID - with better error handling and timeout
        career = fetch_nba_data(PlayerCareerStats, player_id=player['id'], timeout=10)
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        stats = [dict(zip(headers, row)) for row in rows]

        # Store the fetched stats in Redis for future use (with an expiration of 1 hour)
        set_to_cache(cache_key, stats, expiration=3600)

        # Skip background task if worker isn't running properly
        try:
            fetch_player_stats_in_background.delay(player_name)
        except Exception as celery_err:
            logging.warning(f"Background task scheduling error: {str(celery_err)}")

        return jsonify(stats)

    except Timeout:
        logging.error(f"Timeout fetching player stats for {player_name}")
        return jsonify({"error": "Request timed out. Please try again later."}), 503
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
        # Fetch today's NBA scoreboard data - with better error handling
        scoreboard = fetch_nba_data(ScoreBoard, timeout=10)
        data = scoreboard.get_dict()

        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify({"message": "No live games available today.", "games": []}), 200

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

    except Timeout:
        logging.error("Timeout fetching today's games")
        return jsonify({"error": "Request timed out. Please try again later.", "games": []}), 503
    except Exception as e:
        logging.error(f"Error fetching today's games: {str(e)}")
        return jsonify({"error": f"Error fetching today's games. Please try again later.", "games": []}), 500

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
        # Fetch game logs with better error handling
        game_logs = fetch_nba_data(PlayerGameLogs, player_id_nullable=player['id'], last_n_games_nullable=5, timeout=10)
        game_log_data = game_logs.get_dict()['resultSets'][0]
        
        headers = game_log_data['headers']
        rows = game_log_data['rowSet']
        
        if not rows:
            return jsonify({"message": "No recent games found for this player.", "games": []}), 200
            
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

    except Timeout:
        logging.error(f"Timeout fetching last 5 games for {player_name}")
        return jsonify({"error": "Request timed out. Please try again later.", "games": []}), 503
    except Exception as e:
        logging.error(f"Error fetching last 5 games for {player_name}: {str(e)}")
        return jsonify({"error": f"Error fetching last 5 games. Please try again later.", "games": []}), 500

# Route for fetching stats for the static top 10 players with chunking to avoid timeout
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # Check cache first
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
        
    top_players_stats = []

    # Process only 3 players at a time to avoid timeout
    # The full list will be built up over multiple requests
    chunk_size = 3
    current_chunk = request.args.get('chunk', '0')
    
    try:
        current_chunk = int(current_chunk)
    except ValueError:
        current_chunk = 0
    
    # Get previous chunks from cache if they exist
    previous_chunks_key = f"top_players_stats:chunks:{current_chunk-1}"
    previous_chunks = get_from_cache(previous_chunks_key) or []
    
    start_idx = current_chunk * chunk_size
    end_idx = min(start_idx + chunk_size, len(top_players))
    
    # If we've processed all players, return complete list
    if start_idx >= len(top_players):
        if previous_chunks:
            set_to_cache(cache_key, previous_chunks, expiration=43200)
            return jsonify(previous_chunks)
        return jsonify([])
    
    # Process just this chunk of players
    players_to_process = top_players[start_idx:end_idx]
    
    for player_name in players_to_process:
        player = find_player_by_name(player_name)

        if not player:
            continue  # If player not found, skip to the next one

        try:
            # Fetch career stats with better error handling and strict timeout
            career = fetch_nba_data(PlayerCareerStats, player_id=player['id'], timeout=8)
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

        except Timeout:
            logging.error(f"Timeout fetching stats for {player_name}")
            continue
        except Exception as e:
            logging.error(f"Error fetching stats for {player_name}: {str(e)}")
            continue  # Skip to the next player on error
    
    # Combine with previous chunks
    combined_stats = previous_chunks + top_players_stats
    
    # Cache this chunk plus previous chunks
    set_to_cache(f"top_players_stats:chunks:{current_chunk}", combined_stats, expiration=43200)
    
    # If this is the last chunk, cache the complete result
    if end_idx >= len(top_players):
        set_to_cache(cache_key, combined_stats, expiration=43200)
        return jsonify(combined_stats)
    
    # Return partial result with pagination info
    return jsonify({
        "stats": combined_stats, 
        "pagination": {
            "next_chunk": current_chunk + 1,
            "total_chunks": (len(top_players) + chunk_size - 1) // chunk_size,
            "processed": end_idx,
            "total": len(top_players)
        }
    })

# Health check endpoint - needed for Heroku
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  
    app.run(debug=False, host='0.0.0.0', port=port)  # Set debug=False for production