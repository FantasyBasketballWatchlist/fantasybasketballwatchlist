import os
import unicodedata
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, playergamelogs
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players  # Correctly importing players module from nba_api.stats.static

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

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
    if not input_str:
        return ""
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

# Function to search and return player by name
def find_player_by_name(player_name):
    if not player_name:
        return None
        
    # Normalize the player name to handle cases like accents and case sensitivity
    player_name_normalized = remove_accents(player_name.strip().lower())

    # Search for players using the `nba_api` search function
    all_players = players.get_players()  # Correctly using the function from the `players` module
    
    # First, try exact match
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == player_name_normalized:
            return player
            
    # If exact match fails, try partial match (starts with)
    for player in all_players:
        if remove_accents(player['full_name'].lower()).startswith(player_name_normalized):
            return player
            
    return None

# Function to format stats in a consistent order
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
        print(f"Error formatting stats: {str(e)}")
        # Return the original stats if there's an error
        return stats_dict

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

# Route for player stats with robust error handling
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    player_name = request.args.get('player_name')  # Get player name from query parameter
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404  # Error if player isn't found

    try:
        # Fetch career stats using player ID
        career = PlayerCareerStats(player_id=player['id'])
        data = career.get_dict()
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        # Process and format the stats
        all_stats = []
        for row in rows:
            # Create stats dictionary
            stats_dict = dict(zip(headers, row))
            
            # Apply consistent formatting
            formatted_stats = format_stats_in_order(stats_dict)
            all_stats.append(formatted_stats)

        return jsonify(all_stats)
    except Exception as e:
        print(f"Error fetching player stats: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for today's games with caching
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    try:
        # Fetch today's NBA scoreboard data
        games = ScoreBoard()
        data = games.get_dict()

        # Extract games list
        game_list = data['scoreboard']['games']

        if not game_list:
            return jsonify({"error": "No live games available."}), 404

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

        return jsonify(game_data)
    except Exception as e:
        print(f"Error fetching today's games: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for active players with longer caching
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    try:
        # Fetch the full list of players
        all_players = players.get_players()

        if not all_players:
            return jsonify({"error": "No players found."}), 500

        # Filter out only active players
        active_players = [player for player in all_players if player['is_active']]

        # Simplify the response with just player ID and name
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]

        return jsonify(player_data)
    except Exception as e:
        print(f"Error fetching active players: {str(e)}")
        return jsonify({"error": str(e)}), 500

# Route for last 5 games with ordered stats
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400
    
    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404
    
    try:
        # Fetch game logs with increased timeout
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
        
        return jsonify(last_5_games)
    except Exception as e:
        print(f"Error fetching game logs: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for top players stats
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # List to hold the top players' stats
    top_players_stats = {"players": []}

    # Get stats for each player in the top players list
    for player_name in top_players:
        # Search for player based on the name
        player = find_player_by_name(player_name)

        if not player:
            continue  # Skip if player not found

        try:
            # Fetch career stats using player ID
            career = PlayerCareerStats(player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']

            if not rows:
                continue  # Skip if no stats found

            # Process all seasons
            all_seasons = []
            for row in rows:
                stats_dict = dict(zip(headers, row))
                formatted_stats = format_stats_in_order(stats_dict)
                all_seasons.append(formatted_stats)

            # Add player data to the result
            top_players_stats["players"].append({
                "player_name": player_name,
                "player_id": player['id'],
                "stats": all_seasons
            })

        except Exception as e:
            print(f"Error fetching player stats for {player_name}: {str(e)}")

    return jsonify(top_players_stats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)