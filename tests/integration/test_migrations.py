"""The migrations build exactly the schema the models describe, and undo it cleanly."""

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import Base
from tests.integration.alembic_helpers import run_alembic

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


def _diff(connection) -> list:
    context = MigrationContext.configure(
        connection, opts={"compare_type": True, "compare_server_default": True}
    )
    return compare_metadata(context, Base.metadata)


async def test_models_match_the_migrated_schema(async_engine):
    # A model change without its migration (or the other way round) shows up here.
    async with async_engine.connect() as conn:
        diff = await conn.run_sync(_diff)
    assert diff == []


async def test_downgrade_to_base_and_back(pg_url, async_engine):
    # On a database of its own: the session database is shared by the other tests.
    async with async_engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(text("DROP DATABASE IF EXISTS migrations_roundtrip"))
        await autocommit.execute(text("CREATE DATABASE migrations_roundtrip"))

    engine = create_async_engine(pg_url.rsplit("/", 1)[0] + "/migrations_roundtrip")
    try:
        async with engine.connect() as conn:
            autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
            await autocommit.run_sync(run_alembic)
            await autocommit.run_sync(run_alembic, "base", down=True)
            tables = await autocommit.run_sync(lambda c: inspect(c).get_table_names())
            assert set(tables) <= {"alembic_version"}
            await autocommit.run_sync(run_alembic)
            assert await autocommit.run_sync(_diff) == []
    finally:
        await engine.dispose()


_CHECKS_AND_INDEXES = text(
    """
    SELECT 'check ' || c.conname AS name, pg_get_constraintdef(c.oid) AS definition
    FROM pg_constraint c
    JOIN pg_namespace n ON n.oid = c.connamespace
    WHERE c.contype = 'c' AND n.nspname = 'public'
    UNION ALL
    SELECT 'index ' || indexname, indexdef
    FROM pg_indexes
    WHERE schemaname = 'public' AND tablename <> 'alembic_version'
    """
)


async def _checks_and_indexes(engine) -> dict[str, str]:
    async with engine.connect() as conn:
        return {name: definition for name, definition in await conn.execute(_CHECKS_AND_INDEXES)}


async def test_checks_and_indexes_match_the_models(pg_url, async_engine):
    # compare_metadata sees neither the expression of a CHECK constraint nor the predicate
    # of a partial index. Both are compared here as PostgreSQL itself writes them: the
    # migrated database against one built straight from the models.
    async with async_engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(text("DROP DATABASE IF EXISTS models_reference"))
        await autocommit.execute(text("CREATE DATABASE models_reference"))

    reference = create_async_engine(pg_url.rsplit("/", 1)[0] + "/models_reference")
    try:
        async with reference.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        from_models = await _checks_and_indexes(reference)
    finally:
        await reference.dispose()
    from_migrations = await _checks_and_indexes(async_engine)

    assert len(from_models) >= 15  # canary: the query still finds the checks and indexes
    assert from_migrations == from_models
