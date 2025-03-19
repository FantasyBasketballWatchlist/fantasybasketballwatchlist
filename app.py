import os
import unicodedata
import redis
import json
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, PlayerGameLogs
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players
from urllib.parse import urlparse, parse_qs
from requests.exceptions import RequestException, Timeout
from celery import Celery
import logging
import ssl
import time
import threading
from functools import wraps

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

# Set proper SSL configuration for Redis connection
if url.scheme == 'rediss':
    # Add ssl_cert_reqs parameter to URL if not already present
    query_params = parse_qs(url.query)
    
    if 'ssl_cert_reqs' not in query_params:
        # Modify the URL to include ssl_cert_reqs
        if url.query:
            modified_redis_url = f"{redis_url}&ssl_cert_reqs=CERT_NONE"
        else:
            modified_redis_url = f"{redis_url}?ssl_cert_reqs=CERT_NONE"
    else:
        modified_redis_url = redis_url
    
    # Redis client with SSL
    redis_client = redis.StrictRedis(
        host=url.hostname,
        port=url.port,
        password=url.password,
        ssl=True,
        ssl_cert_reqs=ssl.CERT_NONE,
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
# Use the modified URL with ssl_cert_reqs parameter
if url.scheme == 'rediss':
    broker_url = modified_redis_url
    result_backend = modified_redis_url
else:
    broker_url = redis_url
    result_backend = redis_url

# Create Celery app with the modified URLs
celery = Celery(app.name, broker=broker_url, backend=result_backend)

# Important: Set these options for both broker and backend
celery.conf.update(
    broker_transport_options={'ssl_cert_reqs': ssl.CERT_NONE},
    redis_backend_transport_options={'ssl_cert_reqs': ssl.CERT_NONE},
    broker_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE},
    redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE}
)

# Reduce timeout to avoid Heroku H12 errors (30 second limit)
NBA_TIMEOUT = 8  # Reduced from 15 to 8 seconds to ensure we stay well under Heroku's 30s limit

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

# Timeout decorator for functions
def timeout_handler(timeout_duration):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            error = [None]
            
            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    error[0] = e
            
            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(timeout_duration)
            
            if thread.is_alive():
                raise Timeout(f"Function {func.__name__} timed out after {timeout_duration} seconds")
            
            if error[0]:
                raise error[0]
                
            return result[0]
        return wrapper
    return decorator

# Safe NBA data fetching function with timeout handling and retries
def fetch_nba_data(endpoint_class, retries=2, timeout=NBA_TIMEOUT, **kwargs):
    """
    A safer version of the NBA API request function with better error handling, timeout and retries.
    """
    last_error = None
    for attempt in range(retries + 1):
        try:
            # Set timeout to avoid Heroku H12 errors (30s limit)
            kwargs['timeout'] = timeout
            endpoint = endpoint_class(**kwargs)
            return endpoint
        except Timeout:
            logging.error(f"Timeout error fetching NBA data with {endpoint_class.__name__} (attempt {attempt+1}/{retries+1})")
            last_error = Timeout("Request timed out")
            if attempt < retries:
                time.sleep(1)  # Small delay between retries
        except Exception as e:
            logging.error(f"Error initializing NBA endpoint {endpoint_class.__name__}: {str(e)} (attempt {attempt+1}/{retries+1})")
            last_error = e
            if attempt < retries:
                time.sleep(1)  # Small delay between retries
    
    # If we get here, all retries failed
    raise last_error

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
        kwargs['timeout'] = NBA_TIMEOUT
        
    try:
        return request_function(*args, **kwargs).get_dict()
    except Exception as e:
        # Retry up to 3 times
        if self.request.retries < 3:
            raise self.retry(exc=e)
        raise

# Celery Task for background processing
@celery.task
def fetch_player_stats_in_background(player_name):
    player = find_player_by_name(player_name)
    if player:
        try:
            career = PlayerCareerStats(player_id=player['id'], timeout=NBA_TIMEOUT)
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']
            if rows:
                stats = [dict(zip(headers, row)) for row in rows]
                set_to_cache(f"player_stats:{player_name.lower()}", stats)
                return True
        except Exception as e:
            logging.error(f"Background task error for {player_name}: {str(e)}")
    return False

# Mock data generator for fallback when API times out
def generate_mock_player_stats(player_name):
    """Generate mock stats for when the NBA API times out"""
    current_season = '2024-25'
    return {
        "player_name": player_name,
        "note": "This is estimated data due to API timeout. Refresh later for actual stats.",
        "stats": {
            "season": current_season,
            "team": "TEAM",
            "games_played": "N/A",
            "ppg": "N/A",
            "rpg": "N/A",
            "apg": "N/A",
            "fg_pct": "N/A",
            "fg3_pct": "N/A"
        }
    }

# Homepage route
@app.route('/')
def home():
    return render_template('index.html')  # You can replace this with your homepage template

# Route for fetching career stats for a player by name (not ID)
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    start_time = time.time()
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Try to get the stats from Redis cache first
    cache_key = f"player_stats:{player_name.lower()}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        # Schedule background refresh if cache is older than 12 hours
        try:
            cache_ttl = redis_client.ttl(cache_key)
            if cache_ttl < 43200:  # 12 hours in seconds
                try:
                    fetch_player_stats_in_background.delay(player_name)
                except Exception as celery_err:
                    logging.warning(f"Background refresh task error: {str(celery_err)}")
        except Exception as redis_err:
            logging.warning(f"Redis TTL check error: {str(redis_err)}")
            
        return jsonify(cached_stats)  # Return cached data if available

    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404  # Error if player isn't found

    # Check if we're approaching Heroku's 30s timeout limit
    elapsed_time = time.time() - start_time
    if elapsed_time > 20:  # If more than 20 seconds have elapsed
        # Return mock data if we're getting close to timeout
        mock_stats = generate_mock_player_stats(player_name)
        # Try to fetch real data in the background
        try:
            fetch_player_stats_in_background.delay(player_name)
        except Exception as celery_err:
            logging.warning(f"Background task scheduling error: {str(celery_err)}")
        
        return jsonify(mock_stats)

    try:
        # Set a timeout lower than Heroku's 30s limit to ensure we respond
        # Fetch career stats using player ID - with better error handling and timeout
        career = fetch_nba_data(PlayerCareerStats, player_id=player['id'], timeout=NBA_TIMEOUT)
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        stats = [dict(zip(headers, row)) for row in rows]

        # Store the fetched stats in Redis for future use (with an expiration of 24 hours)
        set_to_cache(cache_key, stats, expiration=86400)  # Increased to 24 hours

        return jsonify(stats)

    except Timeout:
        logging.error(f"Timeout fetching player stats for {player_name}")
        # Return a simple response instead of error to avoid breaking the UI
        mock_stats = generate_mock_player_stats(player_name)
        
        # Try to fetch real data in the background
        try:
            fetch_player_stats_in_background.delay(player_name)
        except Exception as celery_err:
            logging.warning(f"Background task scheduling error: {str(celery_err)}")
        
        return jsonify(mock_stats)
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
        scoreboard = fetch_nba_data(ScoreBoard, timeout=NBA_TIMEOUT)
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
        return jsonify({"message": "Unable to fetch live games at this time. Please try again later.", "games": []}), 200
    except Exception as e:
        logging.error(f"Error fetching today's games: {str(e)}")
        return jsonify({"message": "Unable to fetch live games. Please try again later.", "games": []}), 200

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
        game_logs = fetch_nba_data(PlayerGameLogs, player_id_nullable=player['id'], last_n_games_nullable=5, timeout=NBA_TIMEOUT)
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
        return jsonify({"message": "Unable to fetch recent games at this time. Please try again later.", "games": []}), 200
    except Exception as e:
        logging.error(f"Error fetching last 5 games for {player_name}: {str(e)}")
        return jsonify({"message": "Unable to fetch recent games. Please try again later.", "games": []}), 200

# Route for fetching stats for the static top 10 players with chunking to avoid timeout
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # Check cache first
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Return simplified data immediately to avoid timeouts
    simplified_stats = []
    for player_name in top_players:
        # First check if we have this player's stats cached
        player_cache_key = f"player_stats:{player_name.lower()}"
        player_stats = get_from_cache(player_cache_key)
        
        if player_stats:
            # Extract current season stats
            current_season = '2024-25'
            current_season_stats = None
            
            # If player_stats is a list (which it probably is), find the current season
            if isinstance(player_stats, list):
                for season_stat in player_stats:
                    if season_stat.get("SEASON_ID") == current_season:
                        current_season_stats = season_stat
                        break
                
                # If no current season stats, use the most recent one
                if not current_season_stats and player_stats:
                    current_season_stats = player_stats[-1]  # Last item is most recent
            
            if current_season_stats:
                stat_entry = {
                    "player_name": player_name,
                    "stats": {
                        "season": current_season_stats.get("SEASON_ID", "N/A"),
                        "team": current_season_stats.get("TEAM_ABBREVIATION", "N/A"),
                        "games_played": current_season_stats.get("GP", "N/A"),
                        "ppg": current_season_stats.get("PTS", "N/A"),
                        "rpg": current_season_stats.get("REB", "N/A"),
                        "apg": current_season_stats.get("AST", "N/A"),
                        "fg_pct": current_season_stats.get("FG_PCT", "N/A"),
                        "fg3_pct": current_season_stats.get("FG3_PCT", "N/A")
                    }
                }
                simplified_stats.append(stat_entry)
                continue
        
        # If we don't have cached stats, add placeholder
        simplified_stats.append(generate_mock_player_stats(player_name))
        
        # Schedule a background fetch for this player
        try:
            fetch_player_stats_in_background.delay(player_name)
        except Exception as e:
            logging.error(f"Failed to schedule background update for {player_name}: {str(e)}")
    
    # Cache this simplified result for a short time (1 hour)
    set_to_cache(cache_key, simplified_stats, expiration=3600)
    
    return jsonify(simplified_stats)

# Health check endpoint - needed for Heroku
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  
    app.run(debug=False, host='0.0.0.0', port=port)  # Set debug=False for production