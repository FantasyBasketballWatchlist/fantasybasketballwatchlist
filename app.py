import os
import unicodedata
import redis
import json
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, playergamelogs
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

# Configure logging for better debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Top players to highlight - using exact same list from the working code
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

# Function to search and return player by name - using the working implementation
def find_player_by_name(player_name):
    if not player_name:
        return None
    
    # Normalize the player name to handle cases like accents and case sensitivity
    player_name_normalized = remove_accents(player_name.strip().lower())
    
    # Check cache first
    normalized_name = player_name_normalized
    
    # Check memory cache
    if normalized_name in player_id_cache:
        return player_id_cache[normalized_name]
    
    # Check Redis cache
    cache_key = f"player:{normalized_name}"
    cached_player = get_from_cache(cache_key)
    if cached_player:
        player_id_cache[normalized_name] = cached_player
        return cached_player

    # Search for players using the `nba_api` search function (from working code)
    try:
        all_players = players.get_players()
        for player in all_players:
            if remove_accents(player['full_name'].lower()) == player_name_normalized:
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

# Background task for player stats with robust error handling
@celery.task
def fetch_player_stats_in_background(player_name):
    player = find_player_by_name(player_name)
    if not player:
        logger.error(f"Player not found: {player_name}")
        return False
    
    try:
        # Fetch career stats
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        
        # Validate data structure
        if 'resultSets' not in data or not data['resultSets'] or 'rowSet' not in data['resultSets'][0]:
            logger.error(f"Invalid API response format for {player_name}")
            return False
            
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if not rows:
            logger.warning(f"No stats found for {player_name}")
            return False
            
        # Process stats with proper ordering and error handling
        all_stats = []
        for row in rows:
            # Ensure row has the same length as headers
            if len(row) != len(headers):
                # Pad or truncate row to match headers
                if len(row) < len(headers):
                    row = row + [None] * (len(headers) - len(row))
                else:
                    row = row[:len(headers)]
                    
            # Create stats dictionary with proper types
            stats_dict = dict(zip(headers, row))
            
            # Apply consistent formatting to ensure fields are properly processed
            formatted_stats = format_stats_in_order(stats_dict)
            all_stats.append(formatted_stats)
        
        # Cache result
        cache_key = f"player_stats:{player_name.lower()}"
        set_to_cache(cache_key, all_stats, expiration=86400)  # 24 hours
        logger.info(f"Successfully cached {len(all_stats)} stat records for {player_name}")
        return True
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

# Route for player stats with robust error handling
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    player_name = request.args.get('player_name')  # Get player name from query parameter
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400
    
    # Get optional season filter
    season_filter = request.args.get('season')
    
    # Generate cache key based on player name and optional season
    cache_key = f"player_stats:{player_name.lower()}"
    if season_filter:
        cache_key = f"{cache_key}:{season_filter}"
    
    # Check cache first
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404
    
    try:
        # Fetch career stats using player ID
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        
        # Validate data structure
        if 'resultSets' not in data or not data['resultSets'] or 'rowSet' not in data['resultSets'][0]:
            return jsonify({"error": "Invalid API response format"}), 500
            
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404
        
        # Process all stats with robust error handling
        all_stats = []
        for row in rows:
            # Ensure row has the same length as headers
            if len(row) != len(headers):
                # Pad or truncate row to match headers
                if len(row) < len(headers):
                    row = row + [None] * (len(headers) - len(row))
                else:
                    row = row[:len(headers)]
            
            # Create stats dictionary with proper types
            stats_dict = dict(zip(headers, row))
            
            # Apply proper formatting
            formatted_stats = format_stats_in_order(stats_dict)
            all_stats.append(formatted_stats)
        
        # Apply season filter if specified
        if season_filter:
            filtered_stats = [stat for stat in all_stats if stat.get('SEASON_ID') == season_filter]
            stats = filtered_stats
        else:
            stats = all_stats
        
        # Cache result
        set_to_cache(cache_key, stats, expiration=86400)  # 24 hours
        
        # Log a sample of the stats for debugging
        if stats and len(stats) > 0:
            logger.info(f"Sample display_stats for {player_name}: {stats[0].get('display_stats')}")
        
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

# Route for today's games - based on the working code approach
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    cache_key = "today_games"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)
    
    try:
        # Fetch today's NBA scoreboard data - exact approach from working code
        games = ScoreBoard()
        data = games.get_dict()
        
        # Extract games list
        game_list = data['scoreboard']['games']
        
        if not game_list:
            return jsonify({"error": "No live games available."}), 404
        
        # Format the game data - exact approach from working code
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
        return jsonify({"error": str(e)}), 400

# Route for active players - based on the working code approach
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    cache_key = "active_players"
    cached_players = get_from_cache(cache_key)
    
    if cached_players:
        return jsonify(cached_players)
    
    try:
        # Fetch the full list of players - exact approach from working code
        all_players = players.get_players()
        
        if not all_players:
            return jsonify({"error": "No players found."}), 500
        
        # Filter out only active players
        active_players = [player for player in all_players if player['is_active']]
        
        # Simplify the response with just player ID and name
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        # Cache result
        set_to_cache(cache_key, player_data, expiration=86400)  # 24 hours
        
        return jsonify(player_data)
    except Exception as e:
        logger.error(f"Error fetching active players: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Route for last 5 games with ordered stats
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')  # Get player name from query parameter
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400
    
    # Check cache
    cache_key = f"last_5_games:{player_name.lower()}"
    cached_games = get_from_cache(cache_key)
    
    if cached_games:
        return jsonify(cached_games)
    
    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404
    
    try:
        # Fetch game logs using the player ID
        game_logs = playergamelogs(Player_ID=player['id'])
        data = game_logs.get_dict()
        
        if 'resultSets' not in data or len(data['resultSets']) == 0 or len(data['resultSets'][0]['rowSet']) == 0:
            return jsonify({"error": "No game logs available for the player."}), 404
        
        game_log_rows = data['resultSets'][0]['rowSet']
        headers = data['resultSets'][0]['headers']
        
        # Process and return the last 5 games
        games = []
        for row in game_log_rows:
            # Convert row to dict
            game_dict = dict(zip(headers, row))
            
            # Add formatted display stats
            formatted_game = format_stats_in_order(game_dict)
            
            # Create a simplified view with just the key info
            game_summary = {
                "date": game_dict.get("GAME_DATE", "N/A"),
                "home_team": game_dict.get("HOME_TEAM_NAME", game_dict.get("HOME_TEAM_ID", "N/A")),
                "away_team": game_dict.get("VISITOR_TEAM_NAME", game_dict.get("VISITOR_TEAM_ID", "N/A")),
                "home_score": game_dict.get("HOME_TEAM_SCORE", "N/A"),
                "away_score": game_dict.get("VISITOR_TEAM_SCORE", "N/A"),
                "outcome": game_dict.get("WL", "N/A"),
                "display_stats": formatted_game["display_stats"] if "display_stats" in formatted_game else {}
            }
            games.append(game_summary)
        
        # Limit to last 5 games
        last_5_games = games[:5]
        
        # Cache result
        set_to_cache(cache_key, last_5_games, expiration=21600)  # 6 hours
        
        return jsonify(last_5_games)
    except Exception as e:
        logger.error(f"Error fetching game logs: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for top players stats with robust error handling
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    cache_key = "top_players_stats"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Get the season parameter, defaulting to 'all' if not specified
    season_filter = request.args.get('season', 'all')
    
    # List to hold the top players' stats
    top_players_stats = []
    error_players = []
    
    # Static list of top players
    for player_name in top_players:
        # Search for player based on the name
        player = find_player_by_name(player_name)
        
        if not player:
            logger.warning(f"Player not found: {player_name}")
            error_players.append({"player_name": player_name, "error": "Player not found"})
            continue
        
        try:
            # Fetch career stats using player ID
            career = PlayerCareerStats(player_id=player['id'])
            data = career.get_dict()
            
            # Validate data structure
            if 'resultSets' not in data or not data['resultSets'] or 'rowSet' not in data['resultSets'][0]:
                logger.error(f"Invalid API response format for {player_name}")
                error_players.append({"player_name": player_name, "error": "Invalid API response"})
                continue
                
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']
            
            if not rows:
                logger.warning(f"No stats found for {player_name}")
                error_players.append({"player_name": player_name, "error": "No stats available"})
                continue
            
            # Convert all rows to dictionaries with robust error handling
            all_stats = []
            for row in rows:
                # Ensure row has the same length as headers
                if len(row) != len(headers):
                    # Pad or truncate row to match headers
                    if len(row) < len(headers):
                        row = row + [None] * (len(headers) - len(row))
                    else:
                        row = row[:len(headers)]
                
                # Create stats dictionary with proper types
                stats_dict = dict(zip(headers, row))
                
                # Apply robust formatting
                formatted_stats = format_stats_in_order(stats_dict)
                all_stats.append(formatted_stats)
            
            # If specific season is requested (and not 'all'), filter for that season
            if season_filter != 'all':
                filtered_stats = [stat for stat in all_stats if stat.get('SEASON_ID') == season_filter]
                
                if filtered_stats:
                    top_players_stats.append({
                        "player_name": player_name,
                        "player_id": player['id'],
                        "stats": filtered_stats
                    })
                else:
                    logger.warning(f"No stats found for {player_name} in season {season_filter}")
                    error_players.append({
                        "player_name": player_name, 
                        "error": f"No stats for season {season_filter}"
                    })
            else:
                # Return all seasons
                top_players_stats.append({
                    "player_name": player_name,
                    "player_id": player['id'],
                    "stats": all_stats
                })
                
            # Log a sample for debugging
            if all_stats and len(all_stats) > 0:
                logger.info(f"Sample display_stats for {player_name}: {all_stats[0].get('display_stats')}")
        
        except Exception as e:
            logger.error(f"Error fetching player stats for {player_name}: {str(e)}")
            error_players.append({"player_name": player_name, "error": str(e)})
    
    # Add error players to the response if any
    response = {"players": top_players_stats}
    if error_players:
        response["errors"] = error_players
    
    # Cache the result
    if top_players_stats:
        # Don't cache if specific season requested, as the cache key doesn't include the season
        if season_filter == 'all':
            set_to_cache(cache_key, response, expiration=3600)  # 1 hour
    
    return jsonify(response)

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
        response = ScoreBoard()
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