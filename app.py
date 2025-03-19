import os
import unicodedata
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, PlayerGameLogs
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
    "Tyrese Halliburton",
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
    # Normalize the player name to handle cases like accents and case sensitivity
    player_name_normalized = remove_accents(player_name.strip().lower())

    # Check if players is a module and print its type (for debugging purposes)
    print(f"Type of players module: {type(players)}")

    # Search for players using the `nba_api` search function
    all_players = players.get_players()  # Correctly using the function from the `players` module
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == player_name_normalized:
            return player
    return None

# Route to serve the index page without the .html suffix
@app.route('/')
def home():
    return render_template('index.html')

# Route for fetching career stats for a player by name (not ID)
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

        stats = [dict(zip(headers, row)) for row in rows]  # Return the player's stats
        return jsonify(stats)

    except Exception as e:
        print(f"Error occurred while fetching player stats: {str(e)}")  # Debugging log
        return jsonify({"error": str(e)}), 400  # Handle other potential errors

# Route for the trade analyzer page without the .html suffix
@app.route('/trade-analyzer')
def trade_analyzer():
    return render_template('trade-analyzer.html')

# Route for fetching today's NBA scoreboard
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
        print(f"Error occurred while fetching today games: {str(e)}")  # Debugging log
        return jsonify({"error": str(e)}), 400

# Route for fetching active players list (for frontend autocomplete)
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    try:
        # Fetch the full list of players (active and inactive)
        all_players = players.get_players()  # Correctly using the function from the `players` module

        if not all_players:
            return jsonify({"error": "No players found."}), 500  # If no players are found

        # Filter out only active players
        active_players = [player for player in all_players if player['is_active']]

        # Simplify the response with just player ID and name (or any other data you want)
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]

        return jsonify(player_data)  # Return the player data as JSON

    except Exception as e:
        print(f"Error occurred while fetching active players: {str(e)}")  # Debugging log
        return jsonify({"error": str(e)}), 500

# Route for fetching last 5 games for a player
@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')  # Get player name from query parameter
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    # Search for player based on the name
    player = find_player_by_name(player_name)
    
    if not player:
        return jsonify({"error": "Player not found"}), 404  # Player not found in the list

    try:
        # Fetch game logs using the player ID
        game_logs = PlayerGameLogs(player_id_nullable=player['id'], last_n_games_nullable=5)  # Correct parameters
        
        # Extract data from the game logs response
        game_log_data = game_logs.player_game_logs.get_data()

        # Process and return the last 5 games
        last_5_games = []
        for game in game_log_data:
            formatted_game = {
                "date": game.get("GAME_DATE", "N/A"),
                "home_team": game.get("HOME_TEAM_NAME", "N/A"),
                "away_team": game.get("VISITOR_TEAM_NAME", "N/A"),
                "home_score": game.get("HOME_TEAM_SCORE", "N/A"),
                "away_score": game.get("VISITOR_TEAM_SCORE", "N/A"),
                "outcome": game.get("WL", "N/A"),
            }
            last_5_games.append(formatted_game)

        return jsonify(last_5_games)

    except Exception as e:
        print(f"Error occurred while fetching last 5 games: {str(e)}")
        return jsonify({"error": str(e)}), 400

# Route for fetching stats for the static top 10 players, with filtering for 2024-25 season only
@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    # List to hold the top players' stats
    top_players_stats = []

    # Static list of top players, no need to iterate over all players to find them
    for player_name in top_players:
        # Search for player based on the name
        player = find_player_by_name(player_name)

        if not player:
            continue  # If player not found in the list, skip to the next one

        try:
            # Fetch career stats using player ID
            career = PlayerCareerStats(player_id=player['id'])
            data = career.get_dict()
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']

            if not rows:
                continue  # Skip if no stats found for this player

            # Filter for the 2024-25 season stats only
            stats_2024_25 = [
                dict(zip(headers, row)) for row in rows if row[headers.index('SEASON_ID')] == '2024-25'
            ]

            if stats_2024_25:
                season_stats = stats_2024_25[0]  # Assuming one entry per player for 2024-25 season
                top_players_stats.append({
                    "player_name": player_name,
                    "stats": season_stats
                })

        except Exception as e:
            print(f"Error fetching player stats for {player_name}: {str(e)}")

    return jsonify(top_players_stats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use Heroku's dynamic port or 5000 locally
    app.run(debug=True, host='0.0.0.0', port=port)  # Bind to dynamic port for Heroku
