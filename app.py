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
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Get the Redis URL from the environment variable (Heroku Redis URL)
redis_url = os.getenv("REDIS_URL")

# Check if the Redis URL was not found
if not redis_url:
    redis_url = "redis://localhost:6379/0"  # Fallback for local development
    logger.warning("REDIS_URL not set. Using local Redis.")

# Parse the Redis URL
url = urlparse(redis_url)

# Set up Redis with proper SSL configuration
try:
    if url.scheme == 'rediss':
        # For secure Redis connections
        redis_client = redis.StrictRedis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            ssl=True,
            ssl_cert_reqs=ssl.CERT_NONE,
            db=0,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3
        )
        
        # Modified URL for Celery
        modified_redis_url = (
            f"{redis_url}?ssl_cert_reqs=CERT_NONE" 
            if '?' not in redis_url 
            else f"{redis_url}&ssl_cert_reqs=CERT_NONE"
        )
    else:
        # Non-SSL Redis connection
        redis_client = redis.StrictRedis(
            host=url.hostname,
            port=url.port,
            password=url.password,
            ssl=False,
            db=0,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3
        )
        modified_redis_url = redis_url
        
    # Test Redis connection
    redis_client.ping()
    logger.info("Redis connection successful")
except Exception as e:
    logger.error(f"Redis connection error: {str(e)}")
    # Create a dummy redis client for graceful fallback
    class DummyRedis:
        def get(self, key): return None
        def setex(self, key, time, value): return None
        def ttl(self, key): return 0
        def ping(self): return False
    
    redis_client = DummyRedis()
    modified_redis_url = "memory://"
    logger.warning("Using in-memory fallback instead of Redis")

# Celery configuration with proper SSL settings
celery = Celery(app.name)
celery.conf.update(
    broker_url=modified_redis_url,
    result_backend=modified_redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    broker_transport_options={'visibility_timeout': 3600},
    redis_backend_transport_options={'socket_timeout': 5},
    broker_connection_retry_on_startup=True
)

# If using SSL, add specific SSL config
if url.scheme == 'rediss':
    celery.conf.update(
        broker_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE},
        redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE}
    )

# NBA API timeout config - using a reasonable value
NBA_TIMEOUT = 10  # Increased to ensure we get data

# In-memory cache
_cache = {}
CACHE_EXPIRY = {}

# Top players to highlight
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

# Cache for player IDs to avoid repeated lookups
player_id_cache = {}

# Helper function to remove accents from characters
def remove_accents(input_str):
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# Efficient memory cache functions
def memcache_get(key):
    """Get value from memory cache"""
    if key in _cache and key in CACHE_EXPIRY:
        if CACHE_EXPIRY[key] > time.time():
            return _cache[key]
        # Expired
        del _cache[key]
        del CACHE_EXPIRY[key]
    return None

def memcache_set(key, value, expiration=3600):
    """Set value in memory cache"""
    _cache[key] = value
    CACHE_EXPIRY[key] = time.time() + expiration
    return True

# Multi-level cache get function
def get_from_cache(key):
    """Get value from cache (memory first, then Redis)"""
    # Try memory cache first (faster)
    value = memcache_get(key)
    if value is not None:
        return value
    
    # Try Redis cache
    try:
        data = redis_client.get(key)
        if data:
            try:
                value = json.loads(data)
                # Store in memory for faster future access
                memcache_set(key, value)
                return value
            except json.JSONDecodeError:
                return data
    except Exception as e:
        logger.debug(f"Redis get error: {str(e)}")
    
    return None

# Multi-level cache set function
def set_to_cache(key, value, expiration=3600):
    """Set value in cache (both memory and Redis)"""
    # Always set in memory cache
    memcache_set(key, value, expiration)
    
    # Try to set in Redis
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        redis_client.setex(key, expiration, value)
        return True
    except Exception as e:
        logger.debug(f"Redis set error: {str(e)}")
        return False

# Function to search and return player by name
def find_player_by_name(player_name):
    """Find player by name"""
    if not player_name:
        return None
        
    # Normalize name for consistent lookups
    normalized_name = remove_accents(player_name.strip().lower())
    
    # Check in-memory cache first
    if normalized_name in player_id_cache:
        return player_id_cache[normalized_name]
    
    # Then check Redis cache
    cache_key = f"player:{normalized_name}"
    cached_player = get_from_cache(cache_key)
    if cached_player:
        player_id_cache[normalized_name] = cached_player
        return cached_player
    
    # Search through all players - just like the baseline code
    try:
        all_players = players.get_players()
        for player in all_players:
            if remove_accents(player['full_name'].lower()) == normalized_name:
                # Cache for future lookups
                player_id_cache[normalized_name] = player
                set_to_cache(cache_key, player, expiration=604800)  # 1 week
                return player
    except Exception as e:
        logger.error(f"Error loading players list: {str(e)}")
    
    return None

# Background task for fetching player stats
@celery.task
def fetch_player_stats_in_background(player_name, is_top_player=False):
    """Background task to fetch player stats"""
    logger.info(f"Background fetch for {player_name}")
    
    try:
        player = find_player_by_name(player_name)
        if not player:
            logger.warning(f"Player not found: {player_name}")
            return False
        
        cache_key = f"player_stats:{player_name.lower()}"
        
        # Use same approach as baseline code - simple and direct
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if not rows:
            logger.warning(f"No stats found for {player_name}")
            return False
            
        # Process stats - exactly like baseline code
        stats = [dict(zip(headers, row)) for row in rows]
        
        # Cache stats
        set_to_cache(cache_key, stats, expiration=86400)  # 24 hours
        return True
    except Exception as e:
        logger.error(f"Background task error for {player_name}: {str(e)}")
        return False

# Flask route for homepage
@app.route('/')
def home():
    """Serve homepage"""
    return render_template('index.html')

# Route for fetching career stats for a player by name - just like baseline code
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    """Get career stats for a player - using the same approach as baseline code"""
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Check cache first
    cache_key = f"player_stats:{player_name.lower()}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)

    # Find player - just like baseline code
    player = find_player_by_name(player_name)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    try:
        # Use direct approach like baseline code
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        # Format exactly like baseline code
        stats = [dict(zip(headers, row)) for row in rows]
        
        # Cache the results
        set_to_cache(cache_key, stats, expiration=86400)  # 24 hours
        
        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error fetching stats for {player_name}: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for today's games
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    """Get today's NBA games - using baseline approach"""
    cache_key = "today_games"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)
        
    try:
        # Direct approach like baseline
        games = ScoreBoard()
        data = games.get_dict()
        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify({"error": "No live games available."}), 404

        # Format game data
        game_data = []
        for game in game_list:
            game_data.append({
                "home_team": game['homeTeam']['teamName'],
                "away_team": game['awayTeam']['teamName'],
                "home_score": game['homeTeam']['score'],
                "away_score": game['awayTeam']['score'],
                "status": game['gameStatusText']
            })
            
        # Cache results
        set_to_cache(cache_key, game_data, expiration=300)  # 5 minutes
        return jsonify(game_data)

    except Exception as e:
        logger.error(f"Error fetching today's games: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for active players list
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    """Get list of active NBA players - using baseline approach"""
    cache_key = "active_players"
    cached_players = get_from_cache(cache_key)
    
    if cached_players:
        return jsonify(cached_players)
        
    try:
        # Direct approach like baseline
        all_players = players.get_players()
        if not all_players:
            return jsonify({"error": "No players found."}), 500

        # Filter active players - exactly like baseline
        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        # Cache results
        set_to_cache(cache_key, player_data, expiration=86400)  # 24 hours
        return jsonify(player_data)

    except Exception as e:
        logger.error(f"Error fetching active players: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Route for player's recent games
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    """Get player's last 5 games - using baseline approach"""
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Check cache
    cache_key = f"last_5_games:{player_name.lower()}"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)

    # Find player
    player = find_player_by_name(player_name)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    try:
        # Use PlayerGameLogs instead of playergamelogs
        game_logs = PlayerGameLogs(player_id_nullable=player['id'], last_n_games_nullable=5)
        data = game_logs.get_dict()
        
        if 'resultSets' not in data or len(data['resultSets']) == 0 or len(data['resultSets'][0]['rowSet']) == 0:
            return jsonify({"error": "No game logs available for the player."}), 404
            
        # Process game data - like baseline
        headers = data['resultSets'][0]['headers']
        rows = data['resultSets'][0]['rowSet']
        
        games = [dict(zip(headers, row)) for row in rows]
        last_5_games = games[:5]
        
        formatted_games = []
        for game in last_5_games:
            formatted_game = {
                "date": game.get("GAME_DATE", "N/A"),
                "home_team": game.get("HOME_TEAM_NAME", "N/A"),
                "away_team": game.get("VISITOR_TEAM_NAME", "N/A"),
                "home_score": game.get("HOME_TEAM_SCORE", "N/A"),
                "away_score": game.get("VISITOR_TEAM_SCORE", "N/A"),
                "outcome": game.get("WL", "N/A"),
            }
            formatted_games.append(formatted_game)
            
        # Cache results
        set_to_cache(cache_key, formatted_games, expiration=21600)  # 6 hours
        return jsonify(formatted_games)

    except Exception as e:
        logger.error(f"Error fetching last 5 games for {player_name}: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for top players stats - using baseline approach
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    """Get stats for top players - using baseline approach"""
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Using the direct approach from baseline code
    top_players_stats = []
    
    for player_name in top_players:
        player = find_player_by_name(player_name)
        if not player:
            continue
            
        try:
            # Direct fetch like baseline
            career = PlayerCareerStats(player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']
            
            if not rows:
                continue
                
            # Filter for 2024-25 season like baseline
            stats_2024_25 = [
                dict(zip(headers, row)) for row in rows if row[headers.index('SEASON_ID')] == '2024-25'
            ]
            
            if stats_2024_25:
                season_stats = stats_2024_25[0]  # Most recent season
                top_players_stats.append({
                    "player_name": player_name,
                    "stats": season_stats
                })
                
        except Exception as e:
            logger.error(f"Error fetching top player stats for {player_name}: {str(e)}")
    
    # Cache the results
    if top_players_stats:
        set_to_cache(cache_key, top_players_stats, expiration=3600)  # 1 hour
    
    return jsonify(top_players_stats)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": time.time()
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)