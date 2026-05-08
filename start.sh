#!/usr/bin/env bash
# Start script for Render deployment

set -o errexit  # Exit on error

echo "Initializing database schema..."
python -m app.init_db

echo "Starting application..."
exec gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}
