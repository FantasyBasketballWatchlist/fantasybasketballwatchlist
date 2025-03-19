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
from functools import lru_cache

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
    broker_connection_retry_on_startup=True,
    worker_max_tasks_per_child=100,
    task_acks_late=True,
    worker_prefetch_multiplier=1
)

# If using SSL, add specific SSL config
if url.scheme == 'rediss':
    celery.conf.update(
        broker_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE},
        redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE}
    )

# NBA API timeout config
NBA_TIMEOUT = 3  # Very short timeout to avoid Heroku H12 errors

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
    # Clean expired items occasionally
    if len(_cache) > 1000:  # Limit cache size
        clean_expired_cache_items()
    return True

def clean_expired_cache_items():
    """Remove expired items from memory cache"""
    now = time.time()
    expired_keys = [k for k, exp in CACHE_EXPIRY.items() if exp <= now]
    for k in expired_keys:
        if k in _cache:
            del _cache[k]
        if k in CACHE_EXPIRY:
            del CACHE_EXPIRY[k]

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

# Optimized player search
@lru_cache(maxsize=1000)  # Cache up to 1000 player lookups
def find_player_by_name(player_name):
    """Find player by name with efficient caching"""
    if not player_name:
        return None
        
    # Normalize name for consistent lookups
    normalized_name = remove_accents(player_name.strip().lower())
    
    # Check in-memory cache first (fastest)
    if normalized_name in player_id_cache:
        return player_id_cache[normalized_name]
    
    # Check Redis cache
    cache_key = f"player:{normalized_name}"
    cached_player = get_from_cache(cache_key)
    if cached_player:
        player_id_cache[normalized_name] = cached_player
        return cached_player
    
    # Search through API data
    try:
        all_players = players.get_players()
        for player in all_players:
            player_full_name = remove_accents(player['full_name'].lower())
            if player_full_name == normalized_name:
                # Cache result for future lookups
                player_id_cache[normalized_name] = player
                set_to_cache(cache_key, player, expiration=604800)  # Cache for 1 week
                return player
    except Exception as e:
        logger.error(f"Error loading players list: {str(e)}")
    
    return None

# Preload player IDs for frequently accessed players
def preload_player_ids():
    """Preload top player IDs into cache"""
    loaded_count = 0
    for player_name in top_players:
        player = find_player_by_name(player_name)
        if player:
            loaded_count += 1
    
    logger.info(f"Preloaded {loaded_count} player IDs")
    return loaded_count

# Safe NBA data fetching
def fetch_nba_data(endpoint_class, retries=1, **kwargs):
    """Fetch NBA data with timeout and retry logic"""
    if 'timeout' not in kwargs:
        kwargs['timeout'] = NBA_TIMEOUT
        
    last_error = None
    for attempt in range(retries + 1):
        try:
            endpoint = endpoint_class(**kwargs)
            return endpoint
        except (Timeout, RequestException) as e:
            logger.warning(f"NBA API timeout ({attempt+1}/{retries+1}): {str(e)}")
            last_error = e
            if attempt < retries:
                time.sleep(0.5)  # Brief pause between retries
        except Exception as e:
            logger.error(f"NBA API error: {str(e)}")
            last_error = e
            if attempt < retries:
                time.sleep(0.5)
    
    if last_error:
        raise last_error
    raise Exception("Failed to fetch NBA data")

# Background task for fetching player stats
@celery.task(bind=True, max_retries=2, default_retry_delay=5, time_limit=20)
def fetch_player_stats_in_background(self, player_name, is_top_player=False):
    """Background task to fetch player stats"""
    logger.info(f"Background fetch for {player_name}")
    
    try:
        player = find_player_by_name(player_name)
        if not player:
            logger.warning(f"Player not found: {player_name}")
            return False
        
        cache_key = f"player_stats:{player_name.lower()}"
        
        # Skip if we have fresh data already
        cached_data = get_from_cache(cache_key)
        if cached_data and not is_top_player:
            try:
                ttl = redis_client.ttl(cache_key)
                if ttl > 21600:  # 6 hours
                    return False
            except Exception:
                pass
        
        # Fetch player stats
        career = PlayerCareerStats(player_id=player['id'], timeout=NBA_TIMEOUT)
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if not rows:
            logger.warning(f"No stats found for {player_name}")
            return False
            
        # Process stats
        stats = [dict(zip(headers, row)) for row in rows]
        
        # Cache period
        expiration = 86400 * 2 if is_top_player else 86400  # 48 or 24 hours
        set_to_cache(cache_key, stats, expiration=expiration)
        
        # Update top players cache
        if is_top_player:
            update_top_players_stats_cache(player_name, stats)
            
        return True
    except (Timeout, RequestException) as e:
        logger.warning(f"Background task timeout for {player_name}: {str(e)}")
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            self.retry(countdown=self.default_retry_delay * (2 ** self.request.retries))
        return False
    except Exception as e:
        logger.error(f"Background task error for {player_name}: {str(e)}")
        return False

# Extract relevant stats 
def extract_key_stats(stats, season_id='2024-25'):
    """Extract key stats from raw data"""
    if not stats or not isinstance(stats, list):
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
    
    # Find current season stats
    current_season_stats = None
    for stat in stats:
        if stat.get('SEASON_ID') == season_id:
            current_season_stats = stat
            break
    
    # If not found, use most recent
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
    
    # Return relevant stats
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

# Update top players stats cache
def update_top_players_stats_cache(player_name, stats):
    """Update the cache of top players stats"""
    cache_key = "top_players_stats"
    top_stats = get_from_cache(cache_key) or []
    
    # Initialize if empty
    if not top_stats:
        top_stats = [{"player_name": name, "stats": {"note": "Loading..."}} for name in top_players]
    
    # Find and update this player
    found = False
    for i, player_stat in enumerate(top_stats):
        if player_stat["player_name"].lower() == player_name.lower():
            top_stats[i] = {
                "player_name": player_name,
                "stats": extract_key_stats(stats)
            }
            found = True
            break
    
    # If player wasn't in the list, add them
    if not found and player_name in top_players:
        top_stats.append({
            "player_name": player_name,
            "stats": extract_key_stats(stats)
        })
    
    # Cache the updated stats
    set_to_cache(cache_key, top_stats, expiration=3600)  # 1 hour

# Generate placeholder stats
def generate_mock_player_stats(player_name):
    """Generate placeholder stats for when real data is unavailable"""
    return {
        "player_name": player_name,
        "stats": {
            "season": "2024-25",
            "team": "-",
            "games_played": 0,
            "ppg": 0,
            "rpg": 0,
            "apg": 0,
            "fg_pct": 0,
            "fg3_pct": 0,
            "note": "Loading..."
        }
    }

# Initialize app data
def initialize_app_data():
    """Initialize app data and preload caches"""
    preload_player_ids()
    
    # Queue background tasks for top players
    for player_name in top_players:
        try:
            # Use apply_async with specific queue and lower priority
            fetch_player_stats_in_background.apply_async(
                args=[player_name, True],
                expires=300  # Expire task after 5 minutes if not executed
            )
        except Exception as e:
            logger.error(f"Failed to schedule background task: {str(e)}")

# Flask route for homepage
@app.route('/')
def home():
    """Serve homepage with app initialization on first visit"""
    if not player_id_cache:
        try:
            # Initialize in a non-blocking way
            threading.Thread(target=initialize_app_data).start()
        except Exception as e:
            logger.error(f"Error initializing app data: {str(e)}")
    
    return render_template('index.html')

# API route for player stats
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    """Get career stats for a player"""
    start_time = time.time()
    player_name = request.args.get('player_name')
    
    if not player_name:
        return jsonify([]), 400

    # Check cache first
    cache_key = f"player_stats:{player_name.lower()}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        # Ensure it's an array
        if not isinstance(cached_stats, list):
            cached_stats = []
        
        # Schedule refresh if needed
        try:
            ttl = redis_client.ttl(cache_key)
            if ttl < 43200:  # 12 hours
                fetch_player_stats_in_background.delay(player_name, player_name in top_players)
        except Exception:
            pass
            
        return jsonify(cached_stats)

    # Find player
    player = find_player_by_name(player_name)
    if not player:
        return jsonify([]), 404

    # Check for timeout risk
    elapsed_time = time.time() - start_time
    if elapsed_time > 1:
        # Too slow, use background processing
        fetch_player_stats_in_background.delay(player_name, player_name in top_players)
        return jsonify([]), 202

    try:
        # Fetch stats directly
        career = PlayerCareerStats(player_id=player['id'], timeout=NBA_TIMEOUT)
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify([]), 404

        # Process stats
        stats = [dict(zip(headers, row)) for row in rows]
        
        # Cache results
        is_top_player = player_name in top_players
        expiration = 86400 * 2 if is_top_player else 86400  # 48 or 24 hours
        set_to_cache(cache_key, stats, expiration=expiration)
        
        # Update top players stats
        if is_top_player:
            update_top_players_stats_cache(player_name, stats)
        
        return jsonify(stats)

    except Timeout:
        # Handle timeout
        fetch_player_stats_in_background.delay(player_name, player_name in top_players)
        return jsonify([]), 202
    except Exception as e:
        logger.error(f"Error fetching stats for {player_name}: {str(e)}")
        return jsonify([]), 500

# API route for today's games
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    """Get today's NBA games"""
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
        return jsonify([]), 200

# API route for active players
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    """Get list of active NBA players"""
    cache_key = "active_players"
    cached_players = get_from_cache(cache_key)
    
    if cached_players:
        return jsonify(cached_players)
        
    try:
        all_players = players.get_players()
        if not all_players:
            return jsonify([]), 200

        # Filter active players
        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        # Cache results
        set_to_cache(cache_key, player_data, expiration=86400)  # 24 hours
        return jsonify(player_data)

    except Exception as e:
        logger.error(f"Error fetching active players: {str(e)}")
        return jsonify([]), 500

# API route for player's recent games
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    """Get player's last 5 games"""
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify([]), 400

    # Check cache
    cache_key = f"last_5_games:{player_name.lower()}"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)

    # Find player
    player = find_player_by_name(player_name)
    if not player:
        return jsonify([]), 404

    try:
        # Fetch game logs
        game_logs = PlayerGameLogs(
            player_id_nullable=player['id'], 
            last_n_games_nullable=5, 
            timeout=NBA_TIMEOUT
        )
        data = game_logs.get_dict()
        
        if not data.get('resultSets') or not data['resultSets'][0].get('rowSet'):
            return jsonify([]), 200
            
        # Process game data
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
            
        # Cache results
        set_to_cache(cache_key, formatted_games, expiration=21600)  # 6 hours
        return jsonify(formatted_games)

    except Exception as e:
        logger.error(f"Error fetching last 5 games for {player_name}: {str(e)}")
        return jsonify([]), 200

# API route for top players stats
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    """Get stats for top players"""
    # Check cache first
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        # Schedule updates for missing data
        for player_data in cached_stats:
            if "note" in player_data.get("stats", {}) or player_data.get("stats", {}).get("note"):
                try:
                    fetch_player_stats_in_background.delay(player_data["player_name"], True)
                except Exception:
                    pass
        return jsonify(cached_stats)
    
    # No cache, build response with available data
    response_data = []
    
    for player_name in top_players:
        # Try to get player stats from cache
        player_cache_key = f"player_stats:{player_name.lower()}"
        player_stats = get_from_cache(player_cache_key)
        
        if player_stats and isinstance(player_stats, list):
            # We have cached stats
            response_data.append({
                "player_name": player_name,
                "stats": extract_key_stats(player_stats)
            })
        else:
            # Use placeholder and schedule background fetch
            response_data.append(generate_mock_player_stats(player_name))
            try:
                fetch_player_stats_in_background.delay(player_name, True)
            except Exception as e:
                logger.error(f"Failed to schedule background fetch: {str(e)}")
    
    # Cache aggregate response
    set_to_cache(cache_key, response_data, expiration=3600)  # 1 hour
    
    return jsonify(response_data)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy", 
        "timestamp": time.time(),
        "redis": redis_client.ping() if hasattr(redis_client, 'ping') else False,
        "cache_size": len(_cache)
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # Initialize on startup
    threading.Thread(target=initialize_app_data).start()
    # Run app
    app.run(debug=False, host='0.0.0.0', port=port)