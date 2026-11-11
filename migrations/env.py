"""Alembic environment, wired to the app's async engine settings.

Two ways in:
1. CLI (`uv run alembic upgrade head`): builds an async engine from
   settings.DATABASE_URL and runs the migrations on it.
2. Tests: the caller passes an open connection in `config.attributes["connection"]`
   and the migrations run on it.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.db_registry as _db_registry  # noqa: F401 -- registers every table in Base.metadata
from app.core.config import settings
from app.core.db import POOLER_CONNECT_ARGS, Base

config = context.config
target_metadata = Base.metadata

# Logging from alembic.ini, only for the CLI: inside the test suite it would reset the
# loggers the app and pytest configured.
if config.config_file_name is not None and "connection" not in config.attributes:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Render the SQL without connecting (`alembic upgrade head --sql`)."""
    context.configure(
        url=settings.direct_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    section = config.get_section(config.config_ini_section) or {}
    # The direct URL when there is one: DDL and long transactions do not belong in a pooler
    # in transaction mode. Without it they go through the pooler like the app does, with
    # nothing prepared left behind: every run is a new process, whose named statements
    # would meet the ones the run before left on the server connections.
    section["sqlalchemy.url"] = settings.direct_database_url
    through_pooler = settings.DB_TRANSACTION_POOLER and not settings.DB_DIRECT_URL
    engine = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=POOLER_CONNECT_ARGS if through_pooler else {},
    )
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


def run_migrations_online() -> None:
    connection: Connection | None = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
    else:
        asyncio.run(_run_async())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
