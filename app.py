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

# Super short timeout to avoid Heroku H12 errors
NBA_TIMEOUT = 3  # Reduced to 3 seconds to ensure fast responses

# Static list of top 10 players
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

# Pre-cache player IDs to avoid lookups
player_id_cache = {}

# Helper function to remove accents from characters
def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# Function to search and return player by name - with caching
def find_player_by_name(player_name):
    # Check in-memory cache first
    normalized_name = remove_accents(player_name.strip().lower())
    if normalized_name in player_id_cache:
        return player_id_cache[normalized_name]
    
    # Then check Redis cache
    cache_key = f"player:{normalized_name}"
    cached_player = get_from_cache(cache_key)
    if cached_player:
        player_id_cache[normalized_name] = cached_player  # Update in-memory cache
        return cached_player
    
    # If not found, search API
    all_players = players.get_players()
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == normalized_name:
            # Cache this result in both Redis and in-memory
            set_to_cache(cache_key, player, expiration=604800)  # Cache for 1 week
            player_id_cache[normalized_name] = player
            return player
    return None

# Cache helper functions for Redis
def get_from_cache(key):
    try:
        data = redis_client.get(key)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                return data
        return None
    except Exception as e:
        logging.error(f"Redis cache get error: {str(e)}")
        return None

def set_to_cache(key, value, expiration=3600):
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        redis_client.setex(key, expiration, value)
        return True
    except Exception as e:
        logging.error(f"Redis cache set error: {str(e)}")
        return False

# Pre-fetch and cache all player IDs for top players
def preload_player_ids():
    for player_name in top_players:
        find_player_by_name(player_name)
    logging.info(f"Preloaded {len(player_id_cache)} player IDs")

# Simplified NBA data fetching with very short timeout
def fetch_nba_data(endpoint_class, **kwargs):
    if 'timeout' not in kwargs:
        kwargs['timeout'] = NBA_TIMEOUT
    try:
        endpoint = endpoint_class(**kwargs)
        return endpoint
    except Exception as e:
        logging.error(f"Error with {endpoint_class.__name__}: {str(e)}")
        raise

# Celery Task for background processing with priority for top players
@celery.task
def fetch_player_stats_in_background(player_name, is_top_player=False):
    player = find_player_by_name(player_name)
    if not player:
        return False
    
    try:
        cache_key = f"player_stats:{player_name.lower()}"
        
        # Don't waste time refetching if we have recent data
        if not is_top_player and get_from_cache(cache_key):
            ttl = redis_client.ttl(cache_key)
            if ttl > 21600:  # 6 hours
                return False  # Don't refetch if cache is still fresh
        
        career = PlayerCareerStats(player_id=player['id'], timeout=NBA_TIMEOUT)
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if rows:
            stats = [dict(zip(headers, row)) for row in rows]
            # Cache longer for top players
            expiration = 86400 * 2 if is_top_player else 86400  # 48 or 24 hours
            set_to_cache(cache_key, stats, expiration=expiration)
            
            # Update the aggregate top players stats if this is a top player
            if is_top_player:
                update_top_players_stats_cache(player_name, stats)
            
            return True
    except Exception as e:
        logging.error(f"Background task error for {player_name}: {str(e)}")
    return False

# Function to extract relevant stats from full stats for faster processing
def extract_key_stats(stats, season_id='2024-25'):
    current_season_stats = None
    
    # Find current season stats
    for stat in stats:
        if stat.get('SEASON_ID') == season_id:
            current_season_stats = stat
            break
    
    # If not found, use the most recent season
    if not current_season_stats and stats:
        current_season_stats = stats[-1]
    
    if not current_season_stats:
        return {
            "season": "N/A",
            "team": "N/A",
            "games_played": 0,
            "ppg": 0,
            "rpg": 0,
            "apg": 0,
            "fg_pct": 0,
            "fg3_pct": 0
        }
    
    # Return only the key stats we need
    return {
        "season": current_season_stats.get("SEASON_ID", "N/A"),
        "team": current_season_stats.get("TEAM_ABBREVIATION", "N/A"),
        "games_played": current_season_stats.get("GP", 0),
        "ppg": current_season_stats.get("PTS", 0),
        "rpg": current_season_stats.get("REB", 0),
        "apg": current_season_stats.get("AST", 0),
        "fg_pct": current_season_stats.get("FG_PCT", 0),
        "fg3_pct": current_season_stats.get("FG3_PCT", 0)
    }

# Update the aggregated top players stats cache when individual player stats change
def update_top_players_stats_cache(player_name, stats):
    cache_key = "top_players_stats"
    top_stats = get_from_cache(cache_key) or []
    
    # If this is a new cache, initialize with placeholder data
    if not top_stats:
        top_stats = [{"player_name": name, "stats": {"note": "Loading..."}} for name in top_players]
    
    # Find and update this player's stats
    for i, player_stat in enumerate(top_stats):
        if player_stat["player_name"].lower() == player_name.lower():
            top_stats[i] = {
                "player_name": player_name,
                "stats": extract_key_stats(stats)
            }
            break
    
    # Update the cache
    set_to_cache(cache_key, top_stats, expiration=3600)  # 1 hour expiration

# Generate mock stats for immediate response when real data is unavailable
def generate_mock_player_stats(player_name):
    return {
        "player_name": player_name,
        "note": "Stats loading...",
        "stats": {
            "season": "2024-25",
            "team": "-",
            "games_played": "-",
            "ppg": "-",
            "rpg": "-",
            "apg": "-",
            "fg_pct": "-",
            "fg3_pct": "-"
        }
    }

# Function to initialize app data - called manually instead of using before_first_request
def initialize_app_data():
    # Preload top player IDs to make lookups faster
    preload_player_ids()
    
    # Schedule background fetch of top player stats
    for player_name in top_players:
        try:
            fetch_player_stats_in_background.delay(player_name, True)
        except Exception:
            pass

# Flask route for homepage
@app.route('/')
def home():
    # Initialize app data on first request - a replacement for before_first_request
    if not player_id_cache:
        try:
            initialize_app_data()
        except Exception as e:
            logging.error(f"Error initializing app data: {str(e)}")
    
    return render_template('index.html')

# Route for fetching career stats for a player by name
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    start_time = time.time()
    player_name = request.args.get('player_name')
    if not player_name:
        # Return empty array instead of error object
        return jsonify([]), 400

    # Try to get the stats from Redis cache first
    cache_key = f"player_stats:{player_name.lower()}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        # Ensure cached_stats is always an array
        if not isinstance(cached_stats, list):
            cached_stats = []
            
        # Schedule a refresh if data is older than 12 hours
        try:
            ttl = redis_client.ttl(cache_key)
            if ttl < 43200:  # 12 hours
                fetch_player_stats_in_background.delay(player_name, 
                    player_name in top_players)
        except Exception:
            pass
        return jsonify(cached_stats)

    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        # Return empty array for not found
        return jsonify([]), 404

    # Check if we're already getting close to timeout
    elapsed_time = time.time() - start_time
    if elapsed_time > 1:  # If more than 1 second has elapsed
        # Schedule background fetch and return empty array
        fetch_player_stats_in_background.delay(player_name, 
            player_name in top_players)
        return jsonify([]), 202

    try:
        # Use direct and simple approach for immediate fetch
        career = PlayerCareerStats(player_id=player['id'], timeout=NBA_TIMEOUT)
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            # Return empty array if no stats
            return jsonify([]), 404

        stats = [dict(zip(headers, row)) for row in rows]
        
        # Cache the results
        is_top_player = player_name in top_players
        expiration = 86400 * 2 if is_top_player else 86400  # 48 or 24 hours
        set_to_cache(cache_key, stats, expiration=expiration)
        
        # Update top players cache if needed
        if is_top_player:
            update_top_players_stats_cache(player_name, stats)
        
        return jsonify(stats)

    except Timeout:
        # Return empty array for timeout
        fetch_player_stats_in_background.delay(player_name, 
            player_name in top_players)
        return jsonify([]), 202
    except Exception as e:
        logging.error(f"Error fetching stats for {player_name}: {str(e)}")
        # Return empty array for any error
        return jsonify([]), 500

# Route for today's games
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    cache_key = "today_games"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)
        
    try:
        games = ScoreBoard(timeout=NBA_TIMEOUT)
        data = games.get_dict()
        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify([]), 200

        game_data = []
        for game in game_list:
            game_data.append({
                "home_team": game['homeTeam']['teamName'],
                "away_team": game['awayTeam']['teamName'],
                "home_score": game['homeTeam']['score'],
                "away_score": game['awayTeam']['score'],
                "status": game['gameStatusText']
            })
            
        set_to_cache(cache_key, game_data, expiration=300)  # 5 minutes
        return jsonify(game_data)

    except Exception as e:
        logging.error(f"Error fetching today's games: {str(e)}")
        return jsonify([]), 200  # Return empty list instead of error

# Route for active players list
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    cache_key = "active_players"
    cached_players = get_from_cache(cache_key)
    
    if cached_players:
        return jsonify(cached_players)
        
    try:
        all_players = players.get_players()
        if not all_players:
            return jsonify([]), 200

        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        set_to_cache(cache_key, player_data, expiration=86400)  # 24 hours
        return jsonify(player_data)

    except Exception as e:
        logging.error(f"Error fetching active players: {str(e)}")
        return jsonify([]), 500  # Return empty array instead of error object

# Route for last 5 games
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify([]), 400  # Return empty array with error code

    cache_key = f"last_5_games:{player_name.lower()}"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)

    player = find_player_by_name(player_name)
    if not player:
        return jsonify([]), 404  # Return empty array with not found code

    try:
        # Quick direct fetch
        game_logs = PlayerGameLogs(player_id_nullable=player['id'], 
                                  last_n_games_nullable=5, 
                                  timeout=NBA_TIMEOUT)
        data = game_logs.get_dict()
        
        if not data.get('resultSets') or not data['resultSets'][0].get('rowSet'):
            return jsonify([]), 200
            
        headers = data['resultSets'][0]['headers']
        rows = data['resultSets'][0]['rowSet']
        
        formatted_games = []
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
            formatted_games.append(formatted_game)
            
        set_to_cache(cache_key, formatted_games, expiration=21600)  # 6 hours
        return jsonify(formatted_games)

    except Exception as e:
        logging.error(f"Error fetching last 5 games for {player_name}: {str(e)}")
        return jsonify([]), 200  # Return empty list instead of error

# Optimized route for top players stats - returns immediately with available data
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # First check the aggregated cache
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        # Check if we need to refresh any missing players in the background
        for player_data in cached_stats:
            if "note" in player_data.get("stats", {}):
                try:
                    fetch_player_stats_in_background.delay(
                        player_data["player_name"], True)
                except Exception:
                    pass
        return jsonify(cached_stats)
    
    # If no cached aggregate, build a quick response with available data
    response_data = []
    needs_background_update = False
    
    for player_name in top_players:
        # Try to get individual player stats from cache
        player_cache_key = f"player_stats:{player_name.lower()}"
        player_stats = get_from_cache(player_cache_key)
        
        if player_stats:
            # We have this player's stats cached
            response_data.append({
                "player_name": player_name,
                "stats": extract_key_stats(player_stats)
            })
        else:
            # We don't have this player's stats - add placeholder
            response_data.append(generate_mock_player_stats(player_name))
            needs_background_update = True
            
            # Schedule individual background fetch
            try:
                fetch_player_stats_in_background.delay(player_name, True)
            except Exception as e:
                logging.error(f"Failed to schedule background fetch: {str(e)}")
    
    # Cache this aggregate response
    set_to_cache(cache_key, response_data, expiration=3600)  # 1 hour
    
    return jsonify(response_data)

# Health check endpoint for Heroku
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy", "timestamp": time.time()}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  
    app.run(debug=False, host='0.0.0.0', port=port)