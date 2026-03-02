#!/bin/sh
# Entrypoint: run Alembic migrations first, then start the app server.
# This ensures the DB schema is always up-to-date on container start.
set -e

echo "▶ Running Alembic migrations..."

# Detect transition from create_all era:
# If alembic_version table doesn't exist yet, alembic current returns empty.
CURRENT=$(alembic current 2>/dev/null || true)

if [ -z "$CURRENT" ]; then
    echo "  No Alembic version detected. Attempting upgrade head..."
    # Tables may already exist (pre-Alembic DB). Try upgrade; if tables already
    # exist, stamp the DB at head (current state = initial migration applied).
    alembic upgrade head 2>/tmp/alembic_err.txt || {
        if grep -q "already exists" /tmp/alembic_err.txt; then
            echo "  Existing tables found (pre-Alembic DB). Stamping at head..."
            alembic stamp head
            echo "  Stamped. Future migrations will apply normally."
        else
            echo "  ❌ Alembic error:"
            cat /tmp/alembic_err.txt
            exit 1
        fi
    }
else
    alembic upgrade head
fi

echo "✅ Migrations complete."

echo "▶ Starting Uvicorn..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 2
