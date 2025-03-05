from flask import Flask, render_template, jsonify
from nba_api.stats.endpoints import PlayerCareerStats
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Route to serve the index.html page
@app.route('/')
def home():
    return render_template('index.html')

# Route for fetching career stats for a player by ID
@app.route('/api/player_stats/<player_id>', methods=['GET'])
def get_player_stats(player_id):
    try:
        # Fetch career stats
        career = PlayerCareerStats(player_id=player_id)
        data = career.get_dict()

        # Extract stats from resultSets
        result_set = data['resultSets'][0]
        headers = result_set['headers']  # Column names
        rows = result_set['rowSet']  # Player career stats

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        # Convert row data into dictionaries using headers
        stats = [dict(zip(headers, row)) for row in rows]

        return jsonify(stats)

    except Exception as e:
        return jsonify({"error": str(e)}), 400

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
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
