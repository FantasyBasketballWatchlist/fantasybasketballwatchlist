from flask import Flask, render_template, jsonify
from nba_api.stats.endpoints import playercareerstats
from nba_api.live.nba.endpoints import scoreboard
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests

# Route to serve the index.html page
@app.route('/')
def home():
    return render_template('index.html')

# Route for fetching career stats for a player (e.g., Nikola Jokić)
@app.route('/api/player_stats/<player_id>', methods=['GET'])
def get_player_stats(player_id):
    try:
        # Fetch career stats for a player by ID
        career = playercareerstats.PlayerCareerStats(player_id=player_id)
        # Get the stats in dictionary format
        data = career.get_dict()
        
        # You can extract just the relevant data you want
        player_data = data.get('data', [])
        
        if not player_data:
            return jsonify({"error": "Player not found or no stats available."}), 404
        
        # Extract player career stats in a more readable way (you can modify as needed)
        stats = []
        for record in player_data:
            stats.append({
                "season": record[0],
                "team": record[2],  # Team Name
                "games_played": record[6],  # Games Played
                "points": record[27],  # PPG
                "assists": record[28],  # APG
                "rebounds": record[29],  # RPG
                "blocks": record[30],  # BPG
                "steals": record[31],  # SPG
            })
        
        return jsonify(stats)
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Route for fetching today's NBA scoreboard
@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    try:
        # Fetch today's NBA scoreboard data
        games = scoreboard.ScoreBoard()
        data = games.get_dict()  # Get today's scores in dictionary format
        
        # Extract only relevant data
        if 'games' in data:
            game_data = []
            for game in data['games']:
                game_data.append({
                    "home_team": game['homeTeam']['teamName'],
                    "away_team": game['awayTeam']['teamName'],
                    "home_score": game['homeTeam']['score'],
                    "away_score": game['awayTeam']['score'],
                    "status": game['status']
                })
            return jsonify(game_data)
        else:
            return jsonify({"error": "No games data available."}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 400

if __name__ == '__main__':
    app.run(debug=True)
