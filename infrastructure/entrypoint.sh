#!/bin/sh
set -e

if [ "$1" = "api" ]; then
  alembic upgrade head
  exec uvicorn gads_api.main:app --host 0.0.0.0 --port 8000
fi

if [ "$1" = "worker" ]; then
  exec rq worker --url "${REDIS_URL:-redis://redis:6379/0}" gads
fi

exec "$@"
