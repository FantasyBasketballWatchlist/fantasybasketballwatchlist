# Read by gunicorn automatically (Render runs `gunicorn app:app`).
# One process (the ratings live in memory, ~190 MB) with several threads, so a slow request can't block the rest.
workers = 1
threads = 4
timeout = 120
