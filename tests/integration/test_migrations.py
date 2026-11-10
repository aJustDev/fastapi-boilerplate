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
