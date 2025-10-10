#!/usr/bin/env bash
# Start script with database migrations for Render deployment

set -o errexit  # Exit on error

echo "🗄️  Running database migrations..."
alembic upgrade head

echo "🚀 Starting application..."
exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
