"""The engine options the app uses reach PostgreSQL as session settings."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
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


async def test_a_database_error_does_not_carry_the_bound_values(pg_url, async_engine):
    # The exception text is what the handlers log. With the parameters in it, a duplicate
    # registration writes the email and the password hash of the request to the log.
    engine = create_async_engine(pg_url, **ENGINE_OPTIONS)
    insert = text(
        "INSERT INTO users (email, username, password_hash) VALUES (:email, :username, :hash)"
    )
    row = {"email": "leak@example.com", "username": "leak", "hash": "$argon2id$secret-hash"}
    try:
        async with engine.connect() as conn:
            await conn.execute(insert, row)
            with pytest.raises(IntegrityError) as raised:
                await conn.execute(insert, row)
            await conn.rollback()
    finally:
        await engine.dispose()

    # What PostgreSQL itself reports (the constraint, the conflicting key) is still there;
    # the handlers decide how much of that they log.
    message = str(raised.value)
    assert "uq_users_email_lower" in message
    assert "[parameters:" not in message
    assert "secret-hash" not in message
