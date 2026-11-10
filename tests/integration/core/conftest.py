import pytest_asyncio
from sqlalchemy import text

from tests.integration.core.sample import SCHEMA, SampleBase


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def sample_table(async_engine):
    """The table of SampleORM, in its own schema, for the session."""
    async with async_engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        await conn.run_sync(SampleBase.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.execute(text(f"DROP SCHEMA {SCHEMA} CASCADE"))
