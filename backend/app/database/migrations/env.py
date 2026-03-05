"""
Alembic env.py — async-compatible (uses asyncpg driver).

Key design decisions
────────────────────
* We import every ORM model so Alembic's autogenerate can compare
  the current schema against the target metadata.
* We derive the database URL from app.config.settings so credentials
  never live in alembic.ini.
* For async drivers (asyncpg) we use the run_sync/asyncio.run() pattern
  documented in https://alembic.sqlalchemy.org/en/latest/cookbook.html
"""

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

# ── Import the shared DeclarativeBase ────────────────────────────────────────
from app.database.session import Base

# ── Import ALL models so autogenerate picks up every table ───────────────────
# fmt: off
from app.models.admin      import Admin           # noqa: F401
from app.models.student    import Student         # noqa: F401
from app.models.class_     import Class           # noqa: F401
from app.models.device     import Device          # noqa: F401
from app.models.attendance import Attendance      # noqa: F401
from app.models.enrollment import StudentEnrollment  # noqa: F401
# fmt: on

# ── Alembic Config object (provides access to alembic.ini values) ─────────────
config = context.config

# ── Logging (uses alembic.ini [loggers] section) ──────────────────────────────
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── The metadata whose tables drive autogenerate ──────────────────────────────
target_metadata = Base.metadata


# ── Override sqlalchemy.url from application settings ────────────────────────
def get_url() -> str:
    """
    Read DATABASE_URL from the application config.
    This avoids embedding credentials in alembic.ini.
    The URL uses the asyncpg dialect (postgresql+asyncpg://...).
    """
    from app.config import settings
    return settings.DATABASE_URL          # e.g. postgresql+asyncpg://user:pass@host/db


# ─────────────────────────────────────────────────────────────────────────────
# Offline mode — generate SQL script without connecting to the DB
# ─────────────────────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of executing against a live database."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ─────────────────────────────────────────────────────────────────────────────
# Online mode — connect and apply migrations
# ─────────────────────────────────────────────────────────────────────────────

def do_run_migrations(connection: Any) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via run_sync."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,          # no persistent pool during migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point called by Alembic when running in online mode."""
    asyncio.run(run_async_migrations())


# ─────────────────────────────────────────────────────────────────────────────
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
