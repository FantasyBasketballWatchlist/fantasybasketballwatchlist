from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

# Set up the Flask app and Celery configuration
def make_celery(app):
    celery = Celery(
        app.import_name,
        backend=os.environ.get('REDIS_URL'),
        broker=os.environ.get('REDIS_URL')
    )
    celery.conf.update(app.config)
    return celery

celery = make_celery(None)  # Initialize Celery here

# You can use this Celery instance to configure any tasks if needed later.
