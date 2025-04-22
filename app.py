import os
import time
import unicodedata
from flask import Flask, render_template, jsonify, request
from nba_api.stats.static import teams
from nba_api.stats.endpoints import PlayerCareerStats, playergamelog
from nba_api.stats.endpoints import TeamGameLog
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import datetime
import json
import nba_api
import functools

app = Flask(__name__)
CORS(app)

# Static list of top players with a few optimizations
TOP_PLAYERS = tuple([
    "Giannis Antetokounmpo",
])

# Optimized Cache mechanism with bounded LRU behavior
class Cache:
    def __init__(self, max_size=500, expiry_minutes=15):
        self._cache = {}
        self._access_order = []
        self._max_size = max_size
        self._expiry_seconds = expiry_minutes * 60
        self._lock = threading.Lock()
    
    def get(self, key):
        with self._lock:
            if key not in self._cache:
                return None
            
            data, timestamp = self._cache[key]
            
            # Check for expiry
            if time.time() - timestamp > self._expiry_seconds:
                del self._cache[key]
                self._access_order.remove(key)
                return None
            
            # Update access order
            self._access_order.remove(key)
            self._access_order.append(key)
            
            return data
    
    def set(self, key, data):
        with self._lock:
            # Remove if already exists to update
            if key in self._cache:
                self._access_order.remove(key)
            
            # Add to cache
            self._cache[key] = (data, time.time())
            self._access_order.append(key)
            
            # Enforce max size with LRU eviction
            if len(self._cache) > self._max_size:
                oldest_key = self._access_order.pop(0)
                del self._cache[oldest_key]

# Initialize cache
top_players_cache = Cache()

# Robust helper function to remove accents from characters
def remove_accents(input_str):
    try:
        nfkd_form = unicodedata.normalize('NFKD', str(input_str))
        return "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    except Exception:
        return input_str

# Memoized player lookup to reduce redundant searches
_player_lookup_cache = {}
def find_player_by_name(player_name):
    # Normalize the player name once
    player_name_normalized = remove_accents(player_name.strip().lower())
    
    # Check memoized cache first
    if player_name_normalized in _player_lookup_cache:
        return _player_lookup_cache[player_name_normalized]
    
    # Check top players cache
    cache_key = f"player_lookup_{player_name_normalized}"
    cached_player = top_players_cache.get(cache_key)
    if cached_player:
        _player_lookup_cache[player_name_normalized] = cached_player
        return cached_player
    
    # Perform lookup with error handling and memoization
    try:
        all_players = players.get_players()
        for player in all_players:
            player_full_name_normalized = remove_accents(player['full_name'].lower())
            if player_full_name_normalized == player_name_normalized:
                # Cache and memoize the result
                top_players_cache.set(cache_key, player)
                _player_lookup_cache[player_name_normalized] = player
                return player
    except Exception as e:
        print(f"Error in player lookup: {e}")
    
    return None

# Optimization for batch player stats retrieval
def get_multiple_players_stats(player_names):
    results = []
    
    def safe_player_stats(player_name):
        # Reduce redundant lookups
        player = find_player_by_name(player_name)
        
        if not player:
            return {"error": f"Player '{player_name}' not found"}
        
        try:
            # Check cache first
            cache_key = f"top_player_stats_{player_name.lower()}"
            cached_data = top_players_cache.get(cache_key)
            if cached_data:
                return cached_data
            
            # Fetch career stats
            career = PlayerCareerStats(player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']

            if not rows:
                return {"error": f"No stats available for player '{player_name}'"}

            # Filter for the 2024-25 season stats
            stats_2024_25 = [
                dict(zip(headers, row)) for row in rows 
                if row[headers.index('SEASON_ID')] == '2024-25'
            ]

            if stats_2024_25:
                result = {
                    "player_name": player_name,
                    "stats": stats_2024_25[0]
                }
                top_players_cache.set(cache_key, result)
                return result
            else:
                return {"error": f"No 2024-25 stats available for player '{player_name}'"}

        except Exception as e:
            print(f"Error fetching stats for {player_name}: {str(e)}")
            return {"error": f"Error fetching stats for {player_name}: {str(e)}"}
    
    # Use ThreadPoolExecutor with controlled concurrency
    with ThreadPoolExecutor(max_workers=min(5, len(player_names))) as executor:
        future_to_player = {executor.submit(safe_player_stats, name): name for name in player_names}
        for future in as_completed(future_to_player):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                player_name = future_to_player[future]
                results.append({"error": f"Unexpected error for {player_name}: {str(e)}"})
    
    return results

# Optimization for last 5 games retrieval
def get_multiple_players_last_5_games(player_names):
    results = {}
    
    def safe_player_games(player_name):
        # Check cache first
        cache_key = f"last_5_games_{player_name.lower()}"
        cached_data = top_players_cache.get(cache_key)
        
        if cached_data:
            return player_name, cached_data
        
        player = find_player_by_name(player_name)
        
        if not player:
            return player_name, {"error": f"Player '{player_name}' not found"}
        
        try:
            game_log = playergamelog.PlayerGameLog(player_id=player['id'])
            data = game_log.get_data_frames()[0]
            
            if data.empty:
                return player_name, {"error": f"No game logs for player '{player_name}'"}
            
            games = data.head(5).to_dict(orient='records')
            
            # Cache the result
            top_players_cache.set(cache_key, games)
            return player_name, games
        
        except Exception as e:
            print(f"Error fetching last 5 games for {player_name}: {str(e)}")
            return player_name, {"error": f"Error occurred: {str(e)}"}
    
    # Use ThreadPoolExecutor with controlled concurrency
    with ThreadPoolExecutor(max_workers=min(5, len(player_names))) as executor:
        future_to_player = {executor.submit(safe_player_games, name): name for name in player_names}
        for future in as_completed(future_to_player):
            try:
                player_name, player_games = future.result()
                results[player_name] = player_games
            except Exception as e:
                player_name = future_to_player[future]
                results[player_name] = {"error": f"Unexpected error: {str(e)}"}
    
    return results

# Batch processing route for top players stats
@app.route('/api/player_stats/top_players/batch', methods=['GET'])
def get_top_players_stats_batch():
    # Check if we have a cached full response
    cache_key = "all_top_players_batch"
    cached_data = top_players_cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    # Batch processing with all players at once
    top_players_stats = get_multiple_players_stats(TOP_PLAYERS)
    
    # Cache the complete result
    top_players_cache.set(cache_key, top_players_stats)
    
    # Return the results
    return jsonify(top_players_stats)

# Batch processing route for last 5 games
@app.route('/api/last_5_games/batch', methods=['GET'])
def get_last_5_games_batch():
    # Check if we have a cached full response
    cache_key = "all_players_last_5_games_batch"
    cached_data = top_players_cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    # Batch processing with all players at once
    last_5_games_stats = get_multiple_players_last_5_games(TOP_PLAYERS)
    
    # Cache the complete result
    top_players_cache.set(cache_key, last_5_games_stats)
    
    # Return the results
    return jsonify(last_5_games_stats)

# Existing routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404

    try:
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        stats = [dict(zip(headers, row)) for row in rows]
        return jsonify(stats)

    except Exception as e:
        print(f"Error occurred while fetching player stats: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    try:
        # Check cache first
        cache_key = "active_players"
        cached_data = top_players_cache.get(cache_key)
        if cached_data:
            return jsonify(cached_data)
            
        all_players = players.get_players()
        if not all_players:
            return jsonify({"error": "No players found."}), 500

        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]
        
        # Cache the result
        top_players_cache.set(cache_key, player_data)
        
        return jsonify(player_data)

    except Exception as e:
        print(f"Error occurred while fetching active players: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/last_5_games_team', methods=['GET'])
def get_last_5_games_team():
    team_abbreviation = request.args.get('team_abbreviation')  # Updated to match the query parameter

    if not team_abbreviation:
        return jsonify({"error": "Team abbreviation is required"}), 400

    # Team abbreviation mapping
    team_abbr_map = {
        'ATL': 'Atlanta Hawks',
        'BOS': 'Boston Celtics',
        'BKN': 'Brooklyn Nets',
        'CHA': 'Charlotte Hornets',
        'CHI': 'Chicago Bulls',
        'CLE': 'Cleveland Cavaliers',
        'DAL': 'Dallas Mavericks',
        'DEN': 'Denver Nuggets',
        'DET': 'Detroit Pistons',
        'GSW': 'Golden State Warriors',
        'HOU': 'Houston Rockets',
        'IND': 'Indiana Pacers',
        'LAC': 'Los Angeles Clippers',
        'LAL': 'Los Angeles Lakers',
        'MEM': 'Memphis Grizzlies',
        'MIA': 'Miami Heat',
        'MIL': 'Milwaukee Bucks',
        'MIN': 'Minnesota Timberwolves',
        'NOP': 'New Orleans Pelicans',
        'NYK': 'New York Knicks',
        'OKC': 'Oklahoma City Thunder',
        'ORL': 'Orlando Magic',
        'PHI': 'Philadelphia 76ers',
        'PHX': 'Phoenix Suns',
        'POR': 'Portland Trail Blazers',
        'SAC': 'Sacramento Kings',
        'SAS': 'San Antonio Spurs',
        'TOR': 'Toronto Raptors',
        'UTA': 'Utah Jazz',
        'WAS': 'Washington Wizards'
    }

    # Ensure the abbreviation is uppercase and map it to the full team name
    team_name_full = team_abbr_map.get(team_abbreviation.upper())
    if not team_name_full:
        return jsonify({"error": f"Team abbreviation '{team_abbreviation}' not recognized"}), 400

    # Use the nba_api to find the team by name
    all_teams = teams.get_teams()
    team = next((t for t in all_teams if t['full_name'] == team_name_full), None)

    if not team:
        return jsonify({"error": f"Team '{team_name_full}' not found"}), 404

    try:
        # Check cache first
        cache_key = f"last_5_games_team_{team_abbreviation.lower()}"
        cached_data = top_players_cache.get(cache_key)
        if cached_data:
            return jsonify(cached_data)
            
        # Fetch all games for the team in the current season using TeamGameLog
        team_log = TeamGameLog(team_id=team['id'], season='2024-25')  # Specify the season
        data = team_log.get_data_frames()[0]

        if data.empty:
            return jsonify({"error": f"No game logs available for the team '{team_name_full}'."}), 404

        # Get total games played in the season
        total_games_played = len(data)
        
        # Extract detailed information about the last 5 games
        last_5_games = data.head(5).to_dict(orient='records')
        
        # Prepare the response with both games played and last 5 games data
        response = {
            "team": team_name_full,
            "team_abbreviation": team_abbreviation.upper(),
            "total_games_played": total_games_played,
            "last_5_games": last_5_games
        }

        # Cache the result
        top_players_cache.set(cache_key, response)

        # Return the response
        return jsonify(response)

    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": f"Error occurred: {str(e)}"}), 400
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')
    
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400
        
    # Check cache first
    cache_key = f"last_5_games_{player_name.lower()}"
    cached_data = top_players_cache.get(cache_key)
    if cached_data:
        return jsonify(cached_data)
    
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": f"Player '{player_name}' not found"}), 404
        
    try:
        game_log = playergamelog.PlayerGameLog(player_id=player['id'])
        data = game_log.get_data_frames()[0]
        
        if data.empty:
            return jsonify({"error": f"No game logs available for the player '{player_name}'."}), 404
            
        games = data.head(5).to_dict(orient='records')
        
        # Cache the result
        top_players_cache.set(cache_key, games)
        
        return jsonify(games)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({"error": f"Error occurred: {str(e)}"}), 400

@app.route('/api/player_comprehensive_data', methods=['GET'])
def get_player_comprehensive_data():
    player_name = request.args.get('player_name')
    
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400
    
    # Create a comprehensive response dictionary
    comprehensive_data = {
        "player_stats": None,
        "last_5_games_player": None,
        "team_data": {
            "team_name": None,
            "team_abbreviation": None,
            "total_games_played": 0,
            "last_5_games": []
        }
    }
    
    try:
        player = find_player_by_name(player_name)
        
        if not player:
            return jsonify({"error": f"Player '{player_name}' not found"}), 404
        
        # Fetch player career stats
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']
        
        comprehensive_data["player_stats"] = [dict(zip(headers, row)) for row in rows]
        
        # Fetch last 5 games for player
        game_log = playergamelog.PlayerGameLog(player_id=player['id'])
        game_data = game_log.get_data_frames()[0]
        
        if not game_data.empty:
            comprehensive_data["last_5_games_player"] = game_data.head(5).to_dict(orient='records')
        
        # Get team information from current season stats
        current_season_stats = [
            dict(zip(headers, row)) for row in rows 
            if row[headers.index('SEASON_ID')] == '2024-25'
        ]
        
        if current_season_stats:
            current_stats = current_season_stats[0]
            team_abbreviation = current_stats.get('TEAM_ABBREVIATION')
            
            if team_abbreviation:
                # Fetch team's last 5 games
                team_abbr_map = {
                    'ATL': 'Atlanta Hawks',
                    'BOS': 'Boston Celtics',
                    'BKN': 'Brooklyn Nets',
                    'CHA': 'Charlotte Hornets',
                    'CHI': 'Chicago Bulls',
                    'CLE': 'Cleveland Cavaliers',
                    'DAL': 'Dallas Mavericks',
                    'DEN': 'Denver Nuggets',
                    'DET': 'Detroit Pistons',
                    'GSW': 'Golden State Warriors',
                    'HOU': 'Houston Rockets',
                    'IND': 'Indiana Pacers',
                    'LAC': 'Los Angeles Clippers',
                    'LAL': 'Los Angeles Lakers',
                    'MEM': 'Memphis Grizzlies',
                    'MIA': 'Miami Heat',
                    'MIL': 'Milwaukee Bucks',
                    'MIN': 'Minnesota Timberwolves',
                    'NOP': 'New Orleans Pelicans',
                    'NYK': 'New York Knicks',
                    'OKC': 'Oklahoma City Thunder',
                    'ORL': 'Orlando Magic',
                    'PHI': 'Philadelphia 76ers',
                    'PHX': 'Phoenix Suns',
                    'POR': 'Portland Trail Blazers',
                    'SAC': 'Sacramento Kings',
                    'SAS': 'San Antonio Spurs',
                    'TOR': 'Toronto Raptors',
                    'UTA': 'Utah Jazz',
                    'WAS': 'Washington Wizards'
                }
                
                team_name_full = team_abbr_map.get(team_abbreviation)
                
                if team_name_full:
                    all_teams = teams.get_teams()
                    team = next((t for t in all_teams if t['full_name'] == team_name_full), None)
                    
                    if team:
                        team_log = TeamGameLog(team_id=team['id'], season='2024-25')
                        team_data = team_log.get_data_frames()[0]
                        
                        comprehensive_data["team_data"] = {
                            "team_name": team_name_full,
                            "team_abbreviation": team_abbreviation,
                            "total_games_played": len(team_data),
                            "last_5_games": team_data.head(5).to_dict(orient='records')
                        }
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    return jsonify(comprehensive_data)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=True, host='0.0.0.0', port=port)