// JavaScript to handle adding players to the watchlist
const addButtons = document.querySelectorAll('.add-btn');
const watchlist = document.getElementById('watchlist');

// Function to add players to watchlist
addButtons.forEach(button => {
    button.addEventListener('click', function() {
        const playerName = this.parentElement.firstChild.textContent.trim(); // Get the player name
        addToWatchlist(playerName);
    });
});

function addToWatchlist(playerName) {
    // Create a new list item for the watchlist
    const li = document.createElement('li');
    li.textContent = playerName;
    watchlist.appendChild(li);

    // Disable the add button after adding the player
    const playerItem = [...document.querySelectorAll('.player-list li')]
        .find(item => item.firstChild.textContent.trim() === playerName);
    
    const addButton = playerItem.querySelector('.add-btn');
    addButton.disabled = true;
    addButton.textContent = 'Added to Watchlist';
}
