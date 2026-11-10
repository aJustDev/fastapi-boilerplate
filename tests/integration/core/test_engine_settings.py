"""The engine options the app uses reach PostgreSQL as session settings."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.db import ENGINE_OPTIONS

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_statement_and_lock_timeouts_are_set_per_connection(pg_url, async_engine):
    engine = create_async_engine(pg_url, **ENGINE_OPTIONS)
    try:
        async with engine.connect() as conn:
            statement = (await conn.execute(text("SHOW statement_timeout"))).scalar_one()
            lock = (await conn.execute(text("SHOW lock_timeout"))).scalar_one()
    finally:
        await engine.dispose()

    assert statement == f"{settings.DB_STATEMENT_TIMEOUT_MS // 1000}s"
    assert lock == f"{settings.DB_LOCK_TIMEOUT_MS // 1000}s"
