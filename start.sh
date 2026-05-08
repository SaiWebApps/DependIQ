#!/usr/bin/env bash
# Start script with database migrations for Render deployment

set -o errexit  # Exit on error

echo "Running database migrations..."
# Fix stale alembic_version from deleted hand-written migrations.
# If the DB references a revision that no longer exists, stamp to current head.
set +e
MIGRATE_OUTPUT=$(alembic upgrade head 2>&1)
MIGRATE_EXIT=$?
set -e

if [ $MIGRATE_EXIT -ne 0 ]; then
  echo "$MIGRATE_OUTPUT"
  if echo "$MIGRATE_OUTPUT" | grep -q "Can't locate revision"; then
    echo "Stale revision detected. Stamping database to current head..."
    alembic stamp head
  else
    echo "Migration failed for unknown reason. Exiting."
    exit 1
  fi
fi

echo "Starting application..."
exec gunicorn main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}
