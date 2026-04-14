#!/bin/sh
# Entrypoint: run Alembic migrations first, then start the app server.
# This ensures the DB schema is always up-to-date on container start.
set -e

echo "▶ Running Alembic migrations..."

# Detect transition from create_all era:
# If alembic_version table doesn't exist yet, alembic current returns empty.
CURRENT=$(alembic current 2>/dev/null || true)

if [ -z "$CURRENT" ]; then
    echo "  No Alembic version detected. Bootstrapping schema for fresh/pre-Alembic DB..."
    python - <<'PY'
import asyncio
from app.database.session import engine, Base

# Import all models so Base.metadata is fully populated before create_all.
import app.models.admin       # noqa: F401
import app.models.class_      # noqa: F401
import app.models.student     # noqa: F401
import app.models.device      # noqa: F401
import app.models.attendance  # noqa: F401
import app.models.enrollment  # noqa: F401

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

asyncio.run(main())
PY

    echo "  Attempting upgrade head..."
    # If the DB was just bootstrapped to the current schema, Alembic may fail
    # with duplicate table/column errors. In that case, stamp the DB at head.
    alembic upgrade head 2>/tmp/alembic_err.txt || {
        if grep -Eqi "already exists|duplicate|DuplicateTable|DuplicateColumn" /tmp/alembic_err.txt; then
            echo "  Existing/current tables found. Stamping at head..."
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
