import os
import unicodedata
import time
import logging
from flask import Flask, render_template, jsonify, request
from nba_api.stats.endpoints import PlayerCareerStats, playergamelogs
from nba_api.live.nba.endpoints import ScoreBoard
from flask_cors import CORS
from nba_api.stats.static import players
from requests.exceptions import Timeout, RequestException

# Set up logging for Heroku
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

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

def remove_accents(input_str):
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def fetch_with_retry(player_id, retries=3, backoff_factor=2):
    for attempt in range(retries):
        try:
            career = PlayerCareerStats(player_id=player_id)
            data = career.get_dict()
            return data
        except (Timeout, RequestException) as e:
            if attempt < retries - 1:
                sleep_time = backoff_factor ** attempt
                logger.warning(f"Timeout occurred. Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                logger.error(f"Failed to fetch player stats after {retries} attempts.")
                raise e

def find_player_by_name(player_name):
    player_name_normalized = remove_accents(player_name.strip().lower())
    all_players = players.get_players()
    for player in all_players:
        if remove_accents(player['full_name'].lower()) == player_name_normalized:
            return player
    return None

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
        data = fetch_with_retry(player['id'])
        result_set = data['resultSets'][0]
        headers = result_set['headers']
        rows = result_set['rowSet']

        if not rows:
            return jsonify({"error": "Player not found or no stats available."}), 404

        stats = [dict(zip(headers, row)) for row in rows]
        return jsonify(stats)

    except Exception as e:
        logger.error(f"Error occurred while fetching player stats: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/today_games', methods=['GET'])
def get_today_games():
    try:
        games = ScoreBoard()
        data = games.get_dict()

        game_list = data['scoreboard']['games']

        if not game_list:
            return jsonify({"error": "No live games available."}), 404

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
        logger.error(f"Error occurred while fetching today games: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/active_players', methods=['GET'])
def get_active_players():
    try:
        all_players = players.get_players()

        if not all_players:
            return jsonify({"error": "No players found."}), 500

        active_players = [player for player in all_players if player['is_active']]
        player_data = [{"id": player["id"], "name": player["full_name"]} for player in active_players]

        return jsonify(player_data)

    except Exception as e:
        logger.error(f"Error occurred while fetching active players: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/last_5_games', methods=['GET'])
def get_last_5_games():
    player_name = request.args.get('player_name')
    if not player_name:
        return jsonify({"error": "Player name is required"}), 400

    player = find_player_by_name(player_name)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    try:
        game_logs = playergamelogs(Player_ID=player['id'])
        data = game_logs.get_dict()

        if 'resultSets' not in data or len(data['resultSets']) == 0 or len(data['resultSets'][0]['rowSet']) == 0:
            return jsonify({"error": "No game logs available for the player."}), 404

        game_log_rows = data['resultSets'][0]['rowSet']
        headers = data['resultSets'][0]['headers']

        games = [dict(zip(headers, row)) for row in game_log_rows]
        last_5_games = games[:5]

        formatted_games = []
        for game in last_5_games:
            formatted_game = {
                "date": game.get("GAME_DATE", "N/A"),
                "home_team": game.get("HOME_TEAM_ID", "N/A"),
                "away_team": game.get("VISITOR_TEAM_ID", "N/A"),
                "home_score": game.get("HOME_TEAM_SCORE", "N/A"),
                "away_score": game.get("VISITOR_TEAM_SCORE", "N/A"),
                "outcome": game.get("WL", "N/A"),
            }
            formatted_games.append(formatted_game)

        return jsonify(formatted_games)

    except Exception as e:
        logger.error(f"Error occurred while fetching last 5 games: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/api/player_stats/top_players', methods=['GET'])
def get_top_players_stats():
    top_players_stats = []

    for player_name in top_players:
        player = find_player_by_name(player_name)

        if not player:
            continue

        try:
            data = fetch_with_retry(player['id'])
            result_set = data['resultSets'][0]
            headers = result_set['headers']
            rows = result_set['rowSet']

            if not rows:
                continue

            stats_2024_25 = [
                dict(zip(headers, row)) for row in rows if row[headers.index('SEASON_ID')] == '2024-25'
            ]

            if stats_2024_25:
                season_stats = stats_2024_25[0]
                top_players_stats.append({
                    "player_name": player_name,
                    "stats": season_stats
                })

        except Exception as e:
            logger.error(f"Error fetching player stats for {player_name}: {str(e)}")

    return jsonify(top_players_stats)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use Heroku's dynamic port or 5000 locally
    app.run(debug=False, host='0.0.0.0', port=port)  # Use production mode on Heroku