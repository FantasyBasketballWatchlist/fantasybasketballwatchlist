from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from flask import Flask

# Initialize Flask app
app = Flask(__name__)

# Set up the Flask app and Celery configuration
def make_celery(app):
    # Fetch the Redis URL from the environment variable
    redis_url = os.environ.get('REDIS_URL')
    if not redis_url:
        raise ValueError("REDIS_URL environment variable is not set. Make sure to add Heroku Redis add-on.")
    
    # Initialize Celery with Flask app context
    celery = Celery(
        app.import_name,
        backend=redis_url,  # Use Redis as both backend and broker
        broker=redis_url
    )
    celery.conf.update(app.config)
    return celery

# Initialize Celery with the Flask app context
celery = make_celery(app)

# Example of a Celery task
@celery.task
def background_task(arg):
    return f"Processed {arg}"

# Now you can use this Celery instance to configure any tasks in the future.

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  
    app.run(debug=True, host='0.0.0.0', port=port)
