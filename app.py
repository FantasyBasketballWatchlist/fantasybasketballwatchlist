import os
import unicodedata
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, playergamelogs
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players  # Importing players from nba_api

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

# Fetch the full list of players
def fetch_all_players():
    print("Fetching all players...")
    all_players = players.get_players()  # This returns a list of all NBA players (both active and inactive)
    return all_players

# Store players in memory (in real use cases, you might store this in a database)
all_players = fetch_all_players()  # This will store the players once, to prevent calling the API every time

# Route to serve the index.html page
@app.route('/')
def home():
    return render_template('index.html')

# Route for fetching career stats for a player by name (not ID)
@app.route('/api/player_stats', methods=['GET'])
def get_player_stats():
    player_name = request.args.get('player_name')  # Get player name from query parameter
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    player_name = player_name.strip().lower()  # Make sure the name is properly formatted
    player_id = None
    for player in all_players:
        if player['full_name'].lower() == player_name:
            player_id = player['id']
            break

    if not player_id:
        return jsonify({"error": "Player not found"}), 404  # Error if player isn't found

    try:
        # Fetch career stats using player ID
        career = PlayerCareerStats(player_id=player_id)
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

# Route to serve the active players list (for frontend autocomplete)
@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    try:
        # Fetch the full list of players (active and inactive)
        all_players = fetch_all_players()

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

    player_name = player_name.strip().lower()  # Ensure the name is properly formatted
    player_id = None
    for player in all_players:
        if player['full_name'].lower() == player_name:
            player_id = player['id']
            break

    if not player_id:
        return jsonify({"error": "Player not found"}), 404

    try:
        # Fetch game logs using the player ID for the correct season (2024-2025)
        game_logs = playergamelogs.PlayerGameLogs(player_id=player_id, season='2024-25')
        data = game_logs.get_dict()  # Fetch data in a dictionary format instead of pandas DataFrame

        if 'resultSets' not in data or len(data['resultSets']) == 0 or len(data['resultSets'][0]['rowSet']) == 0:
            return jsonify({"error": "No game logs available for the player."}), 404

        # Extract the game logs
        game_log_rows = data['resultSets'][0]['rowSet']
        headers = data['resultSets'][0]['headers']

        # Format the data to return in a more readable format
        games = [dict(zip(headers, row)) for row in game_log_rows]

        # Get the last 5 games (most recent games)
        last_5_games = games[:5]  # Select the first 5 games

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
        # Normalize the player name to avoid issues with accents
        normalized_player_name = remove_accents(player_name.lower())

        # Directly get the player ID using the name from the static list
        player_id = next((p['id'] for p in all_players if remove_accents(p['full_name'].lower()) == normalized_player_name), None)

        if not player_id:
            continue  # If player not found in the list, skip to the next one

        try:
            # Fetch career stats using player ID
            career = PlayerCareerStats(player_id=player_id)
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
