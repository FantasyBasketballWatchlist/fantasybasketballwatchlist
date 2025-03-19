import os
import ssl
from celery import Celery
from urllib.parse import urlparse

# Get the Redis URL from the environment variable
redis_url = os.getenv("REDIS_URL")

# Check if the Redis URL was not found
if not redis_url:
    raise ValueError("REDIS_URL environment variable is not set")

# Create Celery app
celery = Celery('nba_app')

# Configure Celery
celery.conf.broker_url = redis_url
celery.conf.result_backend = redis_url

# Ensure proper SSL configuration for Redis
if redis_url.startswith('rediss://'):
    celery.conf.broker_transport_options = {
        'ssl_cert_reqs': ssl.CERT_NONE
    }
    celery.conf.redis_backend_transport_options = {
        'ssl_cert_reqs': ssl.CERT_NONE
    }

# Import tasks to register them with Celery
from app import retry_nba_api, fetch_player_stats_in_background