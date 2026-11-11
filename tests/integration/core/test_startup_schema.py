"""The schema revision the startup log reads, on a real database."""

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.startup import database_capacity, database_schema, expected_schema

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_a_migrated_database_is_at_the_head_of_the_code(async_engine: AsyncEngine):
    assert await database_schema(async_engine) == expected_schema()


async def test_a_database_never_migrated_has_no_revision(async_engine: AsyncEngine, pg_url):
    # No alembic_version table at all: an empty list, which the log reports as "not
    # migrated", not a failure to read it.
    async with async_engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.execute(text("DROP DATABASE IF EXISTS never_migrated"))
        await autocommit.execute(text("CREATE DATABASE never_migrated"))
    engine = create_async_engine(make_url(pg_url).set(database="never_migrated"))
    try:
        assert await database_schema(engine) == []
    finally:
        await engine.dispose()


async def test_the_connection_limits_of_a_real_server(async_engine: AsyncEngine):
    capacity = await database_capacity(async_engine)

    assert capacity is not None
    assert capacity["max"] >= 1 and capacity["reserved"] >= 0
    assert capacity["in_use"] >= 1, "the query itself holds a connection"
