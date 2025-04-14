#!/bin/bash

# Change to the directory of the script
cd "$(dirname "$0")"

# Run app.py in the background
python3 app.py &

# Start the HTTP server on port 8000
python3 -m http.server 8000

# Keep the terminal open
read -p "Press any key to continue..."
