import os
import unicodedata
import redis
import json
from flask import Flask, render_template, jsonify, request, send_from_directory
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

# Create the static folder if it doesn't exist
os.makedirs(os.path.join(app.root_path, 'static'), exist_ok=True)

# Create the static/js folder if it doesn't exist
os.makedirs(os.path.join(app.root_path, 'static', 'js'), exist_ok=True)

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

# Format stats in a consistent order
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
    
    # Create the data.js file for client-side data.find functionality
    create_data_js_file()

# Function to create data.js file with client-side data.find functionality
def create_data_js_file():
    data_js_content = """// data.js - Client-side data utilities for NBA stats application
// This file provides a data object with find functionality for the frontend

// Main data object to store fetched data and provide search functionality
const data = {
  // Internal storage for player data
  _players: [],
  _gameData: [],
  _stats: {},
  _loaded: false,

  // Method to initialize data from API
  async initialize() {
    if (this._loaded) return true;
    
    try {
      // Fetch active players first
      const playersResponse = await fetch('/api/active_players');
      if (playersResponse.ok) {
        this._players = await playersResponse.json();
      }
      
      // Try to fetch today's games
      try {
        const gamesResponse = await fetch('/api/today_games');
        if (gamesResponse.ok) {
          this._gameData = await gamesResponse.json();
        }
      } catch (e) {
        console.warn('Could not fetch games data:', e);
      }
      
      // Try to fetch top players stats
      try {
        const topPlayersResponse = await fetch('/api/player_stats/top_players');
        if (topPlayersResponse.ok) {
          const topPlayersData = await topPlayersResponse.json();
          if (topPlayersData.players) {
            // Store top players' stats in the stats cache
            topPlayersData.players.forEach(playerData => {
              if (playerData.player_name && playerData.stats) {
                this._stats[playerData.player_name.toLowerCase()] = playerData.stats;
              }
            });
          }
        }
      } catch (e) {
        console.warn('Could not fetch top players stats:', e);
      }
      
      this._loaded = true;
      console.log('Data initialized successfully');
      return true;
    } catch (error) {
      console.error('Error initializing data:', error);
      return false;
    }
  },
  
  // Find method to search through different data collections
  find(collection, query = {}) {
    // Validate inputs
    if (!collection || typeof collection !== 'string') {
      console.error('Collection name must be a string');
      return [];
    }
    
    if (typeof query !== 'object') {
      console.error('Query must be an object');
      return [];
    }
    
    // Initialize data if not already done
    if (!this._loaded) {
      console.warn('Data not initialized. Call data.initialize() first.');
      return [];
    }
    
    // Select the appropriate data collection
    let dataCollection;
    switch(collection.toLowerCase()) {
      case 'players':
        dataCollection = this._players;
        break;
      case 'games':
        dataCollection = this._gameData;
        break;
      case 'stats':
        dataCollection = Object.values(this._stats).flat();
        break;
      default:
        console.error(`Unknown collection: ${collection}`);
        return [];
    }
    
    // If no query is provided or empty query, return all data
    if (!dataCollection || Object.keys(query).length === 0) {
      return Array.isArray(dataCollection) ? [...dataCollection] : [];
    }
    
    // Filter the collection based on query parameters
    return dataCollection.filter(item => {
      if (!item) return false;
      
      return Object.keys(query).every(key => {
        // Handle nested properties with dot notation (e.g., "display_stats.PTS")
        if (key.includes('.')) {
          const parts = key.split('.');
          let value = item;
          
          // Navigate through nested objects
          for (const part of parts) {
            if (value === null || value === undefined || typeof value !== 'object') {
              return false;
            }
            value = value[part];
          }
          
          // Compare the value
          return this._compareValues(value, query[key]);
        }
        
        // Handle regular properties
        return this._compareValues(item[key], query[key]);
      });
    });
  },
  
  // Helper method to fetch a player's stats by name
  async fetchPlayerStats(playerName) {
    if (!playerName) return null;
    
    // Check if we already have the stats cached
    const lowercaseName = playerName.toLowerCase();
    if (this._stats[lowercaseName]) {
      return this._stats[lowercaseName];
    }
    
    try {
      // Fetch from API
      const response = await fetch(`/api/player_stats?player_name=${encodeURIComponent(playerName)}`);
      const data = await response.json();
      
      // Handle in-progress responses
      if (data.status === 'in_progress') {
        console.log(data.message);
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
  
  // Find a player by name (exact or partial match)
  findPlayerByName(name) {
    if (!name) return null;
    
    const normalizedName = name.toLowerCase().trim();
    
    // Try exact match first
    const exactMatch = this._players.find(player => 
      player.name && player.name.toLowerCase() === normalizedName
    );
    
    if (exactMatch) return exactMatch;
    
    // Try partial match
    return this._players.find(player => 
      player.name && player.name.toLowerCase().includes(normalizedName)
    );
  },
  
  // Helper method to compare values with support for regex and comparison operators
  _compareValues(actual, expected) {
    // Handle undefined or null values
    if (actual === undefined || actual === null) {
      return expected === undefined || expected === null;
    }
    
    // Handle regular expressions
    if (expected instanceof RegExp) {
      return expected.test(String(actual));
    }
    
    // Handle comparison objects with operators like $gt, $lt, etc.
    if (typeof expected === 'object' && expected !== null) {
      // MongoDB-like query operators
      if ('$gt' in expected) {
        return actual > expected.$gt;
      }
      if ('$gte' in expected) {
        return actual >= expected.$gte;
      }
      if ('$lt' in expected) {
        return actual < expected.$lt;
      }
      if ('$lte' in expected) {
        return actual <= expected.$lte;
      }
      if ('$ne' in expected) {
        return actual !== expected.$ne;
      }
      if ('$in' in expected && Array.isArray(expected.$in)) {
        return expected.$in.includes(actual);
      }
      
      // Deep equality check for objects
      return JSON.stringify(actual) === JSON.stringify(expected);
    }
    
    // Simple equality for primitive values
    return actual === expected;
  }
};

// Initialize data automatically
document.addEventListener('DOMContentLoaded', () => {
  data.initialize().then(() => {
    console.log('Data system initialized and ready to use');
    // Dispatch an event to notify any listeners that data is ready
    document.dispatchEvent(new CustomEvent('data-ready'));
  });
});

// Examples of how to use data.find:
/*
// Find all players
const allPlayers = data.find('players');

// Find players by partial name match
const lebronPlayers = data.find('players', { name: /lebron/i });

// Find games where home team scored more than 100 points
const highScoringGames = data.find('games', { home_score: { $gt: 100 } });

// Find stats with specific criteria
const goodShooters = data.find('stats', { 'display_stats.FG%': { $gte: 50 } });
*/
"""
    
    # File path for data.js
    file_path = os.path.join(app.root_path, 'static', 'js', 'data.js')
    
    # Write the content to the file
    try:
        with open(file_path, 'w') as f:
            f.write(data_js_content)
        logger.info(f"Created data.js file at {file_path}")
        return True
    except Exception as e:
        logger.error(f"Error creating data.js file: {str(e)}")
        return False