import os
import ssl
from celery import Celery
from urllib.parse import urlparse, parse_qs

# Get the Redis URL from the environment variable
redis_url = os.getenv("REDIS_URL")

# Check if the Redis URL was not found
if not redis_url:
    raise ValueError("REDIS_URL environment variable is not set")

# Parse the Redis URL
url = urlparse(redis_url)

# Modify the URL to include ssl_cert_reqs if necessary
if url.scheme == 'rediss':
    query_params = parse_qs(url.query)
    
    if 'ssl_cert_reqs' not in query_params:
        # Modify the URL to include ssl_cert_reqs
        if url.query:
            modified_redis_url = f"{redis_url}&ssl_cert_reqs=CERT_NONE"
        else:
            modified_redis_url = f"{redis_url}?ssl_cert_reqs=CERT_NONE"
    else:
        modified_redis_url = redis_url
else:
    modified_redis_url = redis_url

# Create Celery app
celery = Celery('app')

# Configure Celery 
celery.conf.update(
    broker_url=modified_redis_url,
    result_backend=modified_redis_url,
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    worker_concurrency=2,
    task_time_limit=15,  # Reduced time limit to avoid long-running tasks
    task_soft_time_limit=10, # Even shorter soft time limit
    broker_connection_retry_on_startup=True
)

# Ensure proper SSL configuration for Redis
if url.scheme == 'rediss':
    celery.conf.update(
        broker_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE},
        redis_backend_use_ssl={'ssl_cert_reqs': ssl.CERT_NONE}
    )

# Import just the fetch_player_stats_in_background function
from app import fetch_player_stats_in_background