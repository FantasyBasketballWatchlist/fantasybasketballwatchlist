// Sample data for players
const players = [
  { id: 1, name: "LeBron James", team: "Los Angeles Lakers", position: "SF", stats: "25 PPG, 7 RPG, 7 APG" },
  { id: 2, name: "Kevin Durant", team: "Brooklyn Nets", position: "PF", stats: "28 PPG, 6 RPG, 5 APG" },
  { id: 3, name: "Stephen Curry", team: "Golden State Warriors", position: "PG", stats: "30 PPG, 5 RPG, 6 APG" },
  { id: 4, name: "Giannis Antetokounmpo", team: "Milwaukee Bucks", position: "PF", stats: "27 PPG, 11 RPG, 6 APG" },
  { id: 5, name: "Kawhi Leonard", team: "Los Angeles Clippers", position: "SF", stats: "24 PPG, 6 RPG, 5 APG" }
];

const playerSearchInput = document.getElementById("player-search");
const searchBtn = document.getElementById("search-btn");
const playerListDiv = document.getElementById("player-list");
const watchlistDiv = document.getElementById("watchlist");

let watchlist = [];

// Display all players
function displayPlayers(filteredPlayers) {
  playerListDiv.innerHTML = "";
  filteredPlayers.forEach(player => {
    const playerItem = document.createElement("div");
    playerItem.classList.add("player-item");
    playerItem.innerHTML = `
      <span>${player.name} (${player.team}) - ${player.position}</span>
      <button onclick="addToWatchlist(${player.id})">Add to Watchlist</button>
    `;
    playerListDiv.appendChild(playerItem);
  });
}

// Display watchlist
function displayWatchlist() {
  watchlistDiv.innerHTML = "";
  if (watchlist.length === 0) {
    watchlistDiv.innerHTML = "<p>Your watchlist is empty!</p>";
  } else {
    watchlist.forEach(player => {
      const watchlistItem = document.createElement("div");
      watchlistItem.classList.add("watchlist-item");
      watchlistItem.innerHTML = `
        <span>${player.name} - ${player.team}</span>
        <button onclick="removeFromWatchlist(${player.id})">Remove</button>
      `;
      watchlistDiv.appendChild(watchlistItem);
    });
  }
}

// Add player to watchlist
function addToWatchlist(playerId) {
  const player = players.find(p => p.id === playerId);
  if (player && !watchlist.includes(player)) {
    watchlist.push(player);
    displayWatchlist();
  }
}

// Remove player from watchlist
function removeFromWatchlist(playerId) {
  watchlist = watchlist.filter(player => player.id !== playerId);
  displayWatchlist();
}

// Search for players based on name
searchBtn.addEventListener("click", () => {
  const searchTerm = playerSearchInput.value.toLowerCase();
  const filteredPlayers = players.filter(player => player.name.toLowerCase().includes(searchTerm));
  displayPlayers(filteredPlayers);
});

// Initial display of all players
displayPlayers(players);
