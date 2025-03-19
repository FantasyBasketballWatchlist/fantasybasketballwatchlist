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
import random

# Add user agent headers to avoid rate limiting
from nba_api.stats.library.http import NBAStatsHTTP
NBAStatsHTTP.nba_response.get_request_dict = getattr(NBAStatsHTTP.nba_response, 'get_request_dict', {})
user_agents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/93.0.4577.82 Safari/537.36',
    'Mozilla/5.0 (iPhone; CPU iPhone OS 14_4_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.141 Safari/537.36 Edg/87.0.664.75',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/70.0.3538.102 Safari/537.36 Edge/18.18363',
]
# Set custom headers to avoid rate limiting
NBAStatsHTTP.nba_response.headers = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
    'Host': 'stats.nba.com',
    'Origin': 'https://www.nba.com',
    'Referer': 'https://www.nba.com/',
    'sec-ch-ua': '" Not A;Brand";v="99", "Chromium";v="90", "Google Chrome";v="90"',
    'sec-ch-ua-mobile': '?0',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'User-Agent': random.choice(user_agents),
    'x-nba-stats-origin': 'stats',
    'x-nba-stats-token': 'true'
}

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
            decode_responses=True
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
            decode_responses=True
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
celery = Celery('app')
celery.conf.update(
    broker_url=modified_redis_url,
    result_backend=modified_redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_concurrency=2,
    broker_connection_retry_on_startup=True
)

# If using SSL, add specific SSL config
if url.scheme == 'rediss':
    celery.conf.update(
        broker_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE},
        redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE}
    )

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

# Cache helper functions
def get_from_cache(key):
    # Check in-memory cache first
    if key in _cache and key in CACHE_EXPIRY:
        if CACHE_EXPIRY[key] > time.time():
            return _cache[key]
        # Expired
        del _cache[key]
        del CACHE_EXPIRY[key]
    
    # Then check Redis
    try:
        data = redis_client.get(key)
        if data:
            try:
                value = json.loads(data)
                # Store in memory too
                _cache[key] = value
                CACHE_EXPIRY[key] = time.time() + 3600  # 1 hour
                return value
            except json.JSONDecodeError:
                return data
    except Exception as e:
        logger.debug(f"Redis error: {str(e)}")
    
    return None

def set_to_cache(key, value, expiration=3600):
    # Set in memory
    _cache[key] = value
    CACHE_EXPIRY[key] = time.time() + expiration
    
    # Set in Redis
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        redis_client.setex(key, expiration, value)
        return True
    except Exception as e:
        logger.debug(f"Redis error: {str(e)}")
        return False

# Function to search and return player by name
def find_player_by_name(player_name):
    if not player_name:
        return None
        
    # Check cache first
    normalized_name = remove_accents(player_name.strip().lower())
    
    # Check memory cache
    if normalized_name in player_id_cache:
        return player_id_cache[normalized_name]
    
    # Check Redis cache
    cache_key = f"player:{normalized_name}"
    cached_player = get_from_cache(cache_key)
    if cached_player:
        player_id_cache[normalized_name] = cached_player
        return cached_player
    
    # Search through players list
    try:
        all_players = players.get_players()
        for player in all_players:
            if remove_accents(player['full_name'].lower()) == normalized_name:
                # Cache for future
                player_id_cache[normalized_name] = player
                set_to_cache(cache_key, player, expiration=604800)  # 1 week
                return player
    except Exception as e:
        logger.error(f"Error getting players list: {str(e)}")
    
    return None

# Preload player IDs for top players
def preload_player_ids():
    loaded = 0
    for player_name in top_players:
        player = find_player_by_name(player_name)
        if player:
            loaded += 1
    
    logger.info(f"Preloaded {loaded} player IDs")
    return loaded

# Implement exponential backoff for NBA API calls
def fetch_from_nba_api(fetch_function, *args, **kwargs):
    max_retries = 3
    base_delay = 1
    
    for attempt in range(1, max_retries + 1):
        try:
            # Randomly select user agent to reduce rate limiting
            NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
            
            # Set a default timeout if not provided
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 15
                
            return fetch_function(*args, **kwargs)
        except (RequestException, Timeout) as e:
            # Calculate delay with exponential backoff and jitter
            delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
            
            if attempt < max_retries:
                logger.warning(f"NBA API request failed: {str(e)}. Retrying in {delay:.2f} seconds...")
                time.sleep(delay)
            else:
                logger.error(f"NBA API request failed after {max_retries} attempts: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error in NBA API call: {str(e)}")
            raise

# Background task for player stats - without mock data fallback
@celery.task
def fetch_player_stats_in_background(player_name):
    player = find_player_by_name(player_name)
    if not player:
        logger.error(f"Player not found: {player_name}")
        return False
    
    try:
        # Use retry mechanism with longer timeout for background tasks
        career = fetch_from_nba_api(
            PlayerCareerStats, 
            player_id=player['id'], 
            timeout=20
        )
        
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if rows:
            stats = [dict(zip(headers, row)) for row in rows]
            cache_key = f"player_stats:{player_name.lower()}"
            set_to_cache(cache_key, stats, expiration=86400)  # 24 hours
            logger.info(f"Successfully cached stats for {player_name}")
            return True
        else:
            logger.warning(f"No stats found for {player_name}")
            return False
    except Exception as e:
        logger.error(f"Background task error for {player_name}: {str(e)}")
        return False

# Initialize app data
def initialize_app():
    # Preload player IDs only
    preload_player_ids()
    
    # Schedule background tasks to fetch stats for top players
    for player_name in top_players:
        # Check if already cached
        cache_key = f"player_stats:{player_name.lower()}"
        if not get_from_cache(cache_key):
            # Schedule fetch in background
            logger.info(f"Scheduling stats fetch for {player_name}")
            fetch_player_stats_in_background.delay(player_name)

# Home route
@app.route('/')
def home():
    # Initialize on first request
    if not player_id_cache:
        initialize_app()
    return render_template('index.html')

# Route for player stats - with retries but no mock data
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400
    
    # Check cache first
    cache_key = f"player_stats:{player_name.lower()}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Find player
    player = find_player_by_name(player_name)
    if not player:
        return jsonify({"error": "Player not found"}), 404
    
    try:
        # Try to fetch data with retry logic
        career = fetch_from_nba_api(
            PlayerCareerStats,
            player_id=player['id'],
            timeout=15
        )
        
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if not rows:
            return jsonify({"error": "No stats available"}), 404
        
        # Process stats
        stats = [dict(zip(headers, row)) for row in rows]
        
        # Cache result
        set_to_cache(cache_key, stats, expiration=86400)  # 24 hours
        
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Error fetching stats for {player_name}: {str(e)}")
        # Try to schedule a background task to fetch it
        fetch_player_stats_in_background.delay(player_name)
        # Return a more informative error
        return jsonify({
            "error": "Stats temporarily unavailable",
            "message": "We're fetching this player's stats in the background. Please try again in a moment."
        }), 202

# Route for today's games
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    cache_key = "today_games"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)
    
    try:
        # Use retry logic
        games = fetch_from_nba_api(ScoreBoard, timeout=15)
        data = games.get_dict()
        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify([]), 200
        
        # Format data
        game_data = []
        for game in game_list:
            game_data.append({
                "home_team": game['homeTeam']['teamName'],
                "away_team": game['awayTeam']['teamName'],
                "home_score": game['homeTeam']['score'],
                "away_score": game['awayTeam']['score'],
                "status": game['gameStatusText']
            })
        
        # Cache result
        set_to_cache(cache_key, game_data, expiration=300)  # 5 minutes
        
        return jsonify(game_data)
    except Exception as e:
        logger.error(f"Error fetching games: {str(e)}")
        return jsonify({"error": "Unable to fetch today's games"}), 503

# Route for active players
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    cache_key = "active_players"
    cached_players = get_from_cache(cache_key)
    
    if cached_players:
        return jsonify(cached_players)
    
    try:
        # Direct approach with custom error handling
        all_players = players.get_players()
        if not all_players:
            return jsonify([]), 200
        
        # Filter active players
        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        # Cache result
        set_to_cache(cache_key, player_data, expiration=86400)  # 24 hours
        
        return jsonify(player_data)
    except Exception as e:
        logger.error(f"Error fetching active players: {str(e)}")
        return jsonify({"error": "Unable to fetch active players"}), 503

# Route for last 5 games
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
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
        # Use retry logic for game logs
        game_logs = fetch_from_nba_api(
            PlayerGameLogs,
            player_id_nullable=player['id'],
            last_n_games_nullable=5,
            timeout=15
        )
        
        data = game_logs.get_dict()
        
        if 'resultSets' not in data or len(data['resultSets']) == 0 or len(data['resultSets'][0]['rowSet']) == 0:
            return jsonify([]), 200
        
        # Process games
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
        
        # Cache result
        set_to_cache(cache_key, formatted_games, expiration=21600)  # 6 hours
        
        return jsonify(formatted_games)
    except Exception as e:
        logger.error(f"Error fetching game logs: {str(e)}")
        return jsonify({"error": "Unable to fetch recent games"}), 503

# Route for top players stats - use real API data with better error handling
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Prepare response using real data
    top_players_stats = []
    missing_players = []
    
    for player_name in top_players:
        # Check individual cache first
        player_cache_key = f"player_stats:{player_name.lower()}"
        player_stats = get_from_cache(player_cache_key)
        
        if player_stats:
            # Find the current season stats
            current_season = '2024-25'
            current_season_stats = None
            
            for stat in player_stats:
                if stat.get('SEASON_ID') == current_season:
                    current_season_stats = stat
                    break
            
            # If found, add to list
            if current_season_stats:
                top_players_stats.append({
                    "player_name": player_name,
                    "stats": current_season_stats
                })
            else:
                # If we have stats but not for current season
                # Add the most recent one instead
                if player_stats:
                    # Sort by season ID in descending order and take the first
                    sorted_stats = sorted(player_stats, 
                                         key=lambda x: x.get('SEASON_ID', ''), 
                                         reverse=True)
                    top_players_stats.append({
                        "player_name": player_name,
                        "stats": sorted_stats[0]
                    })
        else:
            # If not in cache, schedule a background task to fetch
            missing_players.append(player_name)
            fetch_player_stats_in_background.delay(player_name)
    
    # Cache the result if we have some data
    if top_players_stats:
        set_to_cache(cache_key, top_players_stats, expiration=3600)  # 1 hour
    
    # If we're missing more than half the players, return a partial data response
    if len(missing_players) > len(top_players) / 2:
        return jsonify({
            "partial_data": True,
            "available_players": top_players_stats,
            "missing_players": missing_players,
            "message": "Some player data is being fetched in the background. Please try again shortly."
        }), 206
    
    return jsonify(top_players_stats)

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    # Initialize on health check too
    if not player_id_cache:
        initialize_app()
        
    # Check NBA API connectivity by making a simple request
    nba_api_status = "unknown"
    try:
        # Try to get a quick response from the API
        response = fetch_from_nba_api(ScoreBoard, timeout=5)
        if response:
            nba_api_status = "connected"
    except Exception:
        nba_api_status = "disconnected"
        
    return jsonify({
        "status": "healthy", 
        "timestamp": time.time(),
        "cache_size": len(_cache),
        "nba_api_status": nba_api_status
    }), 200

if __name__ == '__main__':
    # Initialize on startup
    initialize_app()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)