#!/bin/sh
# Production entrypoint (Railway): the data refresher in the background, the website in front.
# Both use the database at $DATABASE_URL (Railway's Postgres).
set -e
export PYTHONUNBUFFERED=1

# Refresher: each source updates on its own schedule. Restarts itself if it ever exits.
(
  while true; do
    python -m grove.refresh || true
    echo "refresher exited; restarting in 30s"
    sleep 30
  done
) &

exec gunicorn grove.web:app \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers 2 --threads 4 --timeout 60 \
  --access-logfile -
