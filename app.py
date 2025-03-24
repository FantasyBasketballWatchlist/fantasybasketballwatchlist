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
import threading
from functools import wraps

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

# Celery configuration with proper SSL settings and increased timeouts
celery = Celery('app')
celery.conf.update(
    broker_url=modified_redis_url,
    result_backend=modified_redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_concurrency=2,
    broker_connection_retry_on_startup=True,
    task_time_limit=180,          # Hard limit: 3 minutes
    task_soft_time_limit=120,     # Soft limit: 2 minutes
    worker_max_tasks_per_child=50 # Restart workers after 50 tasks
)

# If using SSL, add specific SSL config
if url.scheme == 'rediss':
    celery.conf.update(
        broker_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE},
        redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE}
    )

# Rate limiting implementation
class RateLimiter:
    def __init__(self, calls_per_second=1):
        self.calls_per_second = calls_per_second
        self.min_interval = 1.0 / calls_per_second
        self.last_call_time = 0
        self.lock = threading.Lock()
    
    def wait(self):
        with self.lock:
            elapsed = time.time() - self.last_call_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_call_time = time.time()

# Create rate limiter for NBA API - 1 call per 1.5 seconds to avoid rate limiting
nba_api_limiter = RateLimiter(calls_per_second=0.67)

# In-memory cache
_cache = {}
CACHE_EXPIRY = {}

# Top players to highlight with correct spelling
top_players = [
    "LeBron James",
    "Giannis Antetokounmpo",
    "Luka Dončić",
    "Tyrese Haliburton",  # Fixed spelling (was Halliburton)
    "Cade Cunningham",
    "Nikola Jokić",
    "Shai Gilgeous-Alexander",
    "Anthony Davis",
    "Victor Wembanyama",
    "Jayson Tatum",
]

# Cache for player IDs to avoid repeated lookups
player_id_cache = {}
all_players_cache = None

# Helper function to remove accents from characters
def remove_accents(input_str):
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# Format stats in a consistent order - this function was missing from your original code
def format_stats_in_order(stats_dict):
    # Create a formatted stats dictionary with primary display stats
    try:
        # Create a normalized version of the stats for display
        display_stats = {}
        
        # Extract key stats if they exist
        if "PTS" in stats_dict:
            display_stats["PTS"] = stats_dict.get("PTS", 0)
        if "REB" in stats_dict:
            display_stats["REB"] = stats_dict.get("REB", 0)
        if "AST" in stats_dict:
            display_stats["AST"] = stats_dict.get("AST", 0)
        if "STL" in stats_dict:
            display_stats["STL"] = stats_dict.get("STL", 0)
        if "BLK" in stats_dict:
            display_stats["BLK"] = stats_dict.get("BLK", 0)
        if "FG_PCT" in stats_dict:
            display_stats["FG%"] = round(stats_dict.get("FG_PCT", 0) * 100, 1) if stats_dict.get("FG_PCT") is not None else 0
        if "FG3_PCT" in stats_dict:
            display_stats["3P%"] = round(stats_dict.get("FG3_PCT", 0) * 100, 1) if stats_dict.get("FG3_PCT") is not None else 0
        if "FT_PCT" in stats_dict:
            display_stats["FT%"] = round(stats_dict.get("FT_PCT", 0) * 100, 1) if stats_dict.get("FT_PCT") is not None else 0
        if "MIN" in stats_dict:
            display_stats["MIN"] = stats_dict.get("MIN", 0)
        if "GP" in stats_dict:
            display_stats["GP"] = stats_dict.get("GP", 0)
        if "SEASON_ID" in stats_dict:
            display_stats["SEASON"] = stats_dict.get("SEASON_ID", "")
            
        # Add the display stats to the original dictionary
        formatted_stats = stats_dict.copy()
        formatted_stats["display_stats"] = display_stats
        
        return formatted_stats
    except Exception as e:
        logger.error(f"Error formatting stats: {str(e)}")
        # Return the original stats if there's an error
        return stats_dict

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

# Function to get all players with caching
def get_all_players():
    global all_players_cache
    
    if all_players_cache is not None:
        return all_players_cache
    
    # Check Redis cache
    cache_key = "all_players"
    cached_players = get_from_cache(cache_key)
    if cached_players:
        all_players_cache = cached_players
        return cached_players
    
    # If not in cache, fetch from API
    try:
        all_players = players.get_players()
        # Cache for 24 hours
        set_to_cache(cache_key, all_players, expiration=86400)
        all_players_cache = all_players
        return all_players
    except Exception as e:
        logger.error(f"Error fetching players list: {str(e)}")
        return []

# Function to search and return player by name with improved error handling
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

    # Search for players using all_players
    all_players = get_all_players()
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == player_name_normalized:
            # Cache for future
            player_id_cache[normalized_name] = player
            set_to_cache(cache_key, player, expiration=604800)  # 1 week
            return player
    
    # Try partial matching if exact match not found
    for player in all_players:
        if remove_accents(player['full_name'].lower()).startswith(player_name_normalized):
            # Cache for future
            player_id_cache[normalized_name] = player
            set_to_cache(cache_key, player, expiration=604800)  # 1 week
            return player
    
    return None

# Batch player lookup
def batch_find_players(player_names):
    results = {}
    not_found = []
    
    for name in player_names:
        player = find_player_by_name(name)
        if player:
            results[name] = player
        else:
            not_found.append(name)
    
    return results, not_found

# Preload player IDs for top players
def preload_player_ids():
    loaded = 0
    for player_name in top_players:
        player = find_player_by_name(player_name)
        if player:
            loaded += 1
    
    logger.info(f"Preloaded {loaded} player IDs")
    return loaded

# Implement exponential backoff for NBA API calls with rate limiting
def fetch_from_nba_api(fetch_function, *args, **kwargs):
    max_retries = 3
    base_delay = 2
    
    for attempt in range(1, max_retries + 1):
        try:
            # Apply rate limiting to avoid NBA API rate limiting
            nba_api_limiter.wait()
            
            # Randomly select user agent to reduce rate limiting detection
            NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
            
            # Set a default timeout if not provided - increased to 45 seconds
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 45
                
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
@celery.task(bind=True, soft_time_limit=120, time_limit=180)
def fetch_player_stats_in_background(self, player_name):
    player = find_player_by_name(player_name)
    if not player:
        logger.error(f"Player not found: {player_name}")
        return False
    
    try:
        # Check cache first to avoid unnecessary API calls
        cache_key = f"player_stats:{player_name.lower()}"
        cached_stats = get_from_cache(cache_key)
        if cached_stats:
            logger.info(f"Using cached stats for {player_name}")
            return True
        
        # Apply rate limiting
        nba_api_limiter.wait()
        
        # Fetch career stats safely with proper error handling
        try:
            # Randomly select user agent
            NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
            
            # Increased timeout
            career = PlayerCareerStats(player_id=player['id'], timeout=45)
            data = career.get_dict()
        except Exception as e:
            logger.error(f"API error for {player_name}: {str(e)}")
            return False
        
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
        
        # Cache result with longer expiration (1 day)
        set_to_cache(cache_key, all_stats, expiration=86400)
        logger.info(f"Successfully cached {len(all_stats)} stat records for {player_name}")
        return True
    except celery.exceptions.SoftTimeLimitExceeded:
        logger.error(f"Task timed out for {player_name}")
        return False
    except Exception as e:
        logger.error(f"Background task error for {player_name}: {str(e)}")
        return False

# Background task for batch fetching player stats
@celery.task(bind=True, soft_time_limit=300, time_limit=360)
def batch_fetch_player_stats(self, player_names):
    results = {}
    
    # Process players one by one with rate limiting
    for name in player_names:
        player = find_player_by_name(name)
        if not player:
            logger.error(f"Player not found: {name}")
            results[name] = {"success": False, "error": "Player not found"}
            continue
        
        try:
            # Check cache first
            cache_key = f"player_stats:{name.lower()}"
            cached_stats = get_from_cache(cache_key)
            if cached_stats:
                logger.info(f"Using cached stats for {name}")
                results[name] = {"success": True}
                continue
            
            # Apply rate limiting and fetch stats
            nba_api_limiter.wait()
            
            # Randomly select user agent
            NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
            
            # Fetch with extended timeout
            career = PlayerCareerStats(player_id=player['id'], timeout=45)
            data = career.get_dict()
            
            # Process and cache stats (similar to fetch_player_stats_in_background)
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']
            
            all_stats = []
            for row in rows:
                if len(row) != len(headers):
                    if len(row) < len(headers):
                        row = row + [None] * (len(headers) - len(row))
                    else:
                        row = row[:len(headers)]
                        
                stats_dict = dict(zip(headers, row))
                formatted_stats = format_stats_in_order(stats_dict)
                all_stats.append(formatted_stats)
            
            # Cache with longer expiration (1 day)
            set_to_cache(cache_key, all_stats, expiration=86400)
            logger.info(f"Successfully cached {len(all_stats)} stat records for {name}")
            results[name] = {"success": True}
            
        except Exception as e:
            logger.error(f"Error fetching stats for {name}: {str(e)}")
            results[name] = {"success": False, "error": str(e)}
    
    return results

# Initialize app data with staggered requests to avoid rate limiting
def initialize_app():
    # Preload player IDs only
    preload_player_ids()
    
    # Staggered schedule for background tasks
    for i, player_name in enumerate(top_players):
        # Check if already cached
        cache_key = f"player_stats:{player_name.lower()}"
        if not get_from_cache(cache_key):
            # Schedule fetch in background with staggered delays
            logger.info(f"Scheduling stats fetch for {player_name}")
            fetch_player_stats_in_background.apply_async(
                args=[player_name],
                countdown=i * 5  # Stagger by 5 seconds per player
            )

# Cache decorator for API endpoints
def cached_endpoint(expiration=3600):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Generate cache key from function name and request arguments
            cache_key = f"{f.__name__}:{request.url}"
            
            # Check cache
            cached_response = get_from_cache(cache_key)
            if cached_response:
                return jsonify(cached_response)
            
            # Call the original function
            result = f(*args, **kwargs)
            
            # Cache the result if it's a successful response
            if isinstance(result, tuple):
                response, status_code = result
                if 200 <= status_code < 300:
                    set_to_cache(cache_key, response, expiration=expiration)
                return jsonify(response), status_code
            else:
                set_to_cache(cache_key, result, expiration=expiration)
                return jsonify(result)
            
        return decorated_function
    return decorator

# Function to get data.find JavaScript
def get_data_find_script():
    """Return the JavaScript for data.find functionality that works with the existing index.html"""
    return """
<script>
// Data object with find functionality
const data = {
  // Storage for player data and stats
  _players: [],
  _stats: {},
  _loaded: false,
  
  // Store highest BPV value for calculations
  _highestBPV: 0,

  // Initialize data by loading from API
  async initialize() {
    if (this._loaded) return true;
    
    try {
      // Use the same API URLs as in the original code
      const apiBaseUrl = 'https://mynewapp000-bf74bc70f33f.herokuapp.com/api';
      
      // Get active players (use the existing players if already loaded)
      if (activePlayers && activePlayers.length > 0) {
        this._players = activePlayers;
      } else {
        const playersResponse = await fetch(`${apiBaseUrl}/active_players`);
        if (playersResponse.ok) {
          this._players = await playersResponse.json();
          // Update the global activePlayers variable to maintain compatibility
          activePlayers = this._players;
        }
      }
      
      // Load top players stats and calculate highest BPV
      try {
        const topPlayersResponse = await fetch(`${apiBaseUrl}/player_stats/top_players`);
        if (topPlayersResponse.ok) {
          const topPlayersData = await topPlayersResponse.json();
          
          if (topPlayersData.players) {
            // Process player stats
            topPlayersData.players.forEach(playerData => {
              if (playerData.player_name && playerData.stats) {
                this._stats[playerData.player_name.toLowerCase()] = playerData.stats;
                
                // Calculate BPV to find highest
                const season = playerData.stats.find(s => s.SEASON_ID === "2024-25");
                if (season) {
                  const playerBPV = calculateBPV(season);
                  if (playerBPV > this._highestBPV) {
                    this._highestBPV = playerBPV;
                  }
                }
              }
            });
            
            // Update the global highestBPV variable for compatibility
            if (this._highestBPV > 0) {
              highestBPV = this._highestBPV;
            }
          }
        }
      } catch (e) {
        console.warn('Could not fetch top players stats:', e);
      }
      
      this._loaded = true;
      console.log('Data system initialized with', this._players.length, 'players');
      return true;
    } catch (error) {
      console.error('Error initializing data:', error);
      return false;
    }
  },
  
  // Find method for players and stats collections
  find(collection) {
    if (!this._loaded) {
      this.initialize();
      return [];
    }
    
    if (collection === 'players') {
      return this._players;
    } else if (collection === 'stats') {
      return Object.values(this._stats).flat();
    }
    
    return [];
  },
  
  // Get player stats by name
  async fetchPlayerStats(playerName) {
    if (!playerName) return null;
    
    // Check cache first
    const lowercaseName = playerName.toLowerCase();
    if (this._stats[lowercaseName]) {
      return this._stats[lowercaseName];
    }
    
    try {
      // Use the same API URL as in the original code
      const apiUrl = 'https://mynewapp000-bf74bc70f33f.herokuapp.com/api/player_stats';
      const response = await fetch(`${apiUrl}?player_name=${encodeURIComponent(playerName)}`);
      const data = await response.json();
      
      if (data.status === 'in_progress') {
        return null;
      }
      
      // Cache the result
      this._stats[lowercaseName] = data;
      return data;
    } catch (error) {
      console.error(`Error fetching stats for ${playerName}:`, error);
      return null;
    }
  },
  
  // Enhanced version of fetchPlayerStats that also updates the UI
  // This can be used to replace the original fetchPlayerStats function
  async fetchAndDisplayPlayerStats(playerName) {
    document.getElementById("spinner").style.display = "block";

    if (!playerName) {
      document.getElementById("loadingMessage").textContent = "Player name is required.";
      document.getElementById("spinner").style.display = "none";
      return;
    }

    try {
      // Get stats using existing data.fetchPlayerStats or from cache
      const stats = await this.fetchPlayerStats(playerName);

      document.getElementById("spinner").style.display = "none";
      document.getElementById("loadingMessage").style.display = "none";

      const tableBody = document.getElementById("playerStatsTable").getElementsByTagName("tbody")[0];
      tableBody.innerHTML = '';

      if (!stats || stats.error) {
        document.getElementById("watchlist").innerHTML = "<p>No results found for the player.</p>";
        return;
      }

      const latestSeason = stats.find((season) => season.SEASON_ID === "2024-25");
      if (!latestSeason) {
        document.getElementById("watchlist").innerHTML = "<p>No data found for the 2024-25 season.</p>";
        return;
      }

      console.log("Latest season stats:", latestSeason);

      const bpv = calculateBPV(latestSeason);
      console.log("Calculated BPV:", bpv);

      const bpvPercentage = (bpv / highestBPV) * 100;

      document.getElementById("bpv-display").textContent = `BPV: ${bpv.toFixed(2)}`;
      // Truncate all decimal points
      let truncatedBpvPercentage = Math.trunc(bpvPercentage);
      document.getElementById("hci-display").textContent = `Heat Check Index: ${truncatedBpvPercentage}`;

      const row = tableBody.insertRow();
      row.innerHTML = ` 
        <td>${formatStat(latestSeason.PTS / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.REB / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.AST / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.BLK / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.STL / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.TOV / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.FGA / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.FGM / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.FTM / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.FTA / latestSeason.GP)}</td>
        <td>${formatStat(latestSeason.FG_PCT * 100)}%</td>
      `;
    } catch (error) {
      console.error("Error fetching player data:", error);
      document.getElementById("loadingMessage").textContent = "Failed to load player stats.";
      document.getElementById("spinner").style.display = "none";
    }
  },
// Find player by name
  findPlayerByName(name) {
    if (!name) return null;
    
    const normalizedName = normalizeString(name);
    
    // Try exact match first
    const exactMatch = this._players.find(player => 
      normalizeString(player.name) === normalizedName
    );
    
    if (exactMatch) return exactMatch;
    
    // Try partial match
    return this._players.find(player => 
      normalizeString(player.name).includes(normalizedName)
    );
  },
  
  // Get array of player suggestions based on partial name
  getPlayerSuggestions(partialName) {
    if (!partialName) return [];
    
    const normalizedQuery = normalizeString(partialName);
    return this._players.filter(player => 
      normalizeString(player.name).includes(normalizedQuery)
    );
  }
};

// Initialize data when the page loads
document.addEventListener('DOMContentLoaded', () => {
  // Initialize the data object
  data.initialize();
  
  // You can optionally update the search event listeners to use data.find
  // This keeps the original code working while adding the new functionality
  const searchBtn = document.getElementById("search-btn");
  if (searchBtn) {
    // Add an alternative event listener
    searchBtn.addEventListener("click", function(e) {
      // Do nothing if the original event was handled
      if (e.processed) return;
      
      const playerName = document.getElementById('player-search').value.trim();
      if (playerName) {
        // Use our enhanced function instead
        data.fetchAndDisplayPlayerStats(playerName);
        document.getElementById('autocomplete-container').innerHTML = '';
      } else {
        document.getElementById("watchlist").innerHTML = "<p>Please enter a player name to search.</p>";
      }
    });
  }
});
</script>
"""

# Home route
@app.route('/')
def home():
    # Initialize on first request
    if not player_id_cache:
        initialize_app()
    
    # Get the original HTML content
    html_content = render_template('index.html')
    
    # Insert data.find script just before the closing </body> tag
    data_find_script = get_data_find_script()
    if '</body>' in html_content:
        modified_html = html_content.replace('</body>', f'{data_find_script}\n</body>')
    else:
        # If no </body> tag, just append it at the end
        modified_html = html_content + data_find_script
    
    return modified_html

# Route for player stats with robust error handling and caching
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
    
    # Check if task is already in progress
    in_progress_key = f"task_in_progress:{player_name.lower()}"
    if get_from_cache(in_progress_key):
        return jsonify({
            "status": "in_progress",
            "message": f"Stats for {player_name} are being fetched. Please try again in a few moments."
        }), 202
    
    try:
        # Set in-progress flag
        set_to_cache(in_progress_key, True, expiration=60)
        
        # Try to get from cache without season filter first
        base_cache_key = f"player_stats:{player_name.lower()}"
        base_cached_stats = get_from_cache(base_cache_key)
        
        if base_cached_stats:
            # If we have base stats and need to filter by season
            if season_filter:
                filtered_stats = [stat for stat in base_cached_stats if stat.get('SEASON_ID') == season_filter]
                if filtered_stats:
                    # Cache the filtered result
                    set_to_cache(cache_key, filtered_stats, expiration=86400)
                    return jsonify(filtered_stats)
            else:
                # Return unfiltered stats
                return jsonify(base_cached_stats)
        
        # If we get here, we need to fetch from the API
        # Schedule background task and return a 202 response
        fetch_player_stats_in_background.delay(player_name)
        
        return jsonify({
            "status": "in_progress",
            "message": f"Stats for {player_name} are being fetched in the background. Please try again in a few moments."
        }), 202
    except Exception as e:
        logger.error(f"Error fetching stats for {player_name}: {str(e)}")
        # Clear in-progress flag on error
        set_to_cache(in_progress_key, None, expiration=1)
        
        # Try to schedule a background task to fetch it
        fetch_player_stats_in_background.delay(player_name)
        
        # Return a more informative error
        return jsonify({
            "error": "Stats temporarily unavailable",
            "message": "We're fetching this player's stats in the background. Please try again in a moment."
        }), 202

# Route for batch player stats
@app.route('/api/batch_player_stats', methods=['POST'])
def get_batch_player_stats():
    data = request.json
    if not data or 'player_names' not in data:
        return jsonify({"error": "player_names array is required"}), 400
    
    player_names = data['player_names']
    if not isinstance(player_names, list) or not player_names:
        return jsonify({"error": "player_names must be a non-empty array"}), 400
    
    # Season filter (optional)
    season_filter = data.get('season')
    
    # Limit batch size to prevent abuse
    if len(player_names) > 20:
        return jsonify({"error": "Maximum 20 players allowed per batch"}), 400
    
    # Check which players are already cached
    cached_results = {}
    players_to_fetch = []
    
    for name in player_names:
        # Generate cache key
        cache_key = f"player_stats:{name.lower()}"
        if season_filter:
            cache_key = f"{cache_key}:{season_filter}"
        
        # Check cache
        cached_stats = get_from_cache(cache_key)
        if cached_stats:
            cached_results[name] = cached_stats
        else:
            players_to_fetch.append(name)
    
    # If all players are cached, return immediately
    if not players_to_fetch:
        return jsonify({"status": "complete", "results": cached_results})
    
    # Check which players exist
    player_lookup = {}
    not_found = []
    
    for name in players_to_fetch:
        player = find_player_by_name(name)
        if player:
            player_lookup[name] = player
        else:
            not_found.append(name)
    
    # Schedule background task for players that need fetching
    if player_lookup:
        players_to_fetch = list(player_lookup.keys())
        batch_fetch_player_stats.delay(players_to_fetch)
    
    # Return partial results
    return jsonify({
        "status": "partial",
        "results": cached_results,
        "pending": players_to_fetch,
        "not_found": not_found,
        "message": "Some player stats are being fetched in the background. Please try again in a few moments for complete results."
    }), 202

# Route for today's games with caching
@app.route('/api/today_games', methods=['GET'])
@cached_endpoint(expiration=300)  # Cache for 5 minutes
def get_today_games():
    try:
        # Fetch today's NBA scoreboard data with rate limiting
        nba_api_limiter.wait()
        
        # Randomly select user agent
        NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
        
        games = ScoreBoard()
        data = games.get_dict()
        
        # Extract games list
        game_list = data['scoreboard']['games']
        
        if not game_list:
            return {"error": "No live games available."}, 404
        
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
        
        return game_data
    except Exception as e:
        logger.error(f"Error fetching games: {str(e)}")
        return {"error": str(e)}, 400

# Route for active players with longer caching
@app.route('/api/active_players', methods=['GET'])
@cached_endpoint(expiration=86400)  # Cache for 24 hours
def get_active_players():
    try:
        # Get all players with caching
        all_players = get_all_players()
        
        if not all_players:
            return {"error": "No players found."}, 500
        
        # Filter out only active players
        active_players = [player for player in all_players if player['is_active']]
        
        # Simplify the response with just player ID and name
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        return player_data
    except Exception as e:
        logger.error(f"Error fetching active players: {str(e)}")
        return {"error": str(e)}, 500

# Route for last 5 games with ordered stats
@app.route('/api/last_5_games', methods=['GET'])
@cached_endpoint(expiration=21600)  # Cache for 6 hours
def get_last_5_games():
    player_name = request.args.get('player_name')
    if not player_name:
        return {"error": "Player name is required"}, 400
    
    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return {"error": "Player not found"}, 404
    
    try:
        # Apply rate limiting
        nba_api_limiter.wait()
        
        # Set random user agent
        NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
        
        # Fetch game logs with increased timeout
        game_logs = playergamelogs(
            Player_ID=player['id'],
            timeout=45
        )
        data = game_logs.get_dict()
        
        if 'resultSets' not in data or len(data['resultSets']) == 0 or len(data['resultSets'][0]['rowSet']) == 0:
            return {"error": "No game logs available for the player."}, 404
        
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
        
        return last_5_games
    except Exception as e:
        logger.error(f"Error fetching game logs: {str(e)}")
        return {"error": str(e)}, 400

# Route for top players stats with robust error handling and caching
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # Get the season parameter, defaulting to 'all' if not specified
    season_filter = request.args.get('season', 'all')
    
    # Generate cache key based on season filter
    cache_key = f"top_players_stats:{season_filter}"
    cached_stats = get_from_cache(cache_key)
    
    if cached_stats:
        return jsonify(cached_stats)
    
    # Check which players are already cached
    cached_players = {}
    players_to_fetch = []
    
    for player_name in top_players:
        stats_key = f"player_stats:{player_name.lower()}"
        if season_filter != 'all':
            stats_key = f"{stats_key}:{season_filter}"
        
        player_stats = get_from_cache(stats_key)
        if player_stats:
            player = find_player_by_name(player_name)
            if player:
                cached_players[player_name] = {
                    "player_name": player_name,
                    "player_id": player['id'],
                    "stats": player_stats
                }
        else:
            players_to_fetch.append(player_name)
    
    # If all players are cached, build and return the full response
    if not players_to_fetch:
        response = {"players": list(cached_players.values())}
        # Cache for 1 hour
        set_to_cache(cache_key, response, expiration=3600)
        return jsonify(response)
    
    # Schedule background fetch for missing players
    if players_to_fetch:
        batch_fetch_player_stats.delay(players_to_fetch)
    
    # Return partial data with pending players
    response = {
        "status": "partial",
        "players": list(cached_players.values()),
        "pending": players_to_fetch,
        "message": "Some player stats are being fetched in the background. Please try again in a few moments for complete results."
    }
    
    return jsonify(response), 202

# Health check endpoint
@app.route('/health', methods=['GET'])
def health_check():
    # Initialize on health check too
    if not player_id_cache:
        initialize_app()
        
    # Check NBA API connectivity by making a very simple request
    nba_api_status = "unknown"
    try:
        # Rate limit this check
        nba_api_limiter.wait()
        
        # Set random user agent
        NBAStatsHTTP.nba_response.headers['User-Agent'] = random.choice(user_agents)
        
        # Try to get a quick response from the API
        response = ScoreBoard()
        if response:
            nba_api_status = "connected"
    except Exception:
        nba_api_status = "disconnected"
        
    # Check Redis status
    redis_status = "connected" if redis_client.ping() else "disconnected"
    
    # Get cache stats
    cache_stats = {
        "memory_cache_size": len(_cache),
        "player_cache_size": len(player_id_cache),
    }
    
    return jsonify({
        "status": "healthy", 
        "timestamp": time.time(),
        "cache": cache_stats,
        "nba_api_status": nba_api_status,
        "redis_status": redis_status
    }), 200

if __name__ == '__main__':
    # Initialize on startup
    initialize_app()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)