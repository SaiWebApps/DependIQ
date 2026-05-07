#!/usr/bin/env bash
# Start script with database migrations for Render deployment

set -o errexit  # Exit on error

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}
