# A local copy of the Render service, used by refresh.py to test code changes before they go live:
# Python 3.13, requirements.txt, `gunicorn app:app --timeout 120`, offline mode. refresh.py runs it with
# Render's limits (0.5 CPU, 512 MB).
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV NBA_OFFLINE=1 NBA_CACHE_DIR=/app/data/live PORT=10000
CMD ["gunicorn", "app:app", "--timeout", "120", "--bind", "0.0.0.0:10000"]
