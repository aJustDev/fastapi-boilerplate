"""The engine behind a real pooler in transaction mode: what breaks, and what the settings fix.

A connection is lent per transaction, so nothing may live on it in between. The
`pgbouncer_url` fixture is the worst case: one server connection shared by every client
and no support for prepared statements.
"""

import asyncio

import asyncpg
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.db import engine_options, set_timeouts_per_transaction
from app.core.events.worker import CHANNEL
from tests.integration.core.sample import SampleORM, SampleRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def pooled_engine(pgbouncer_url):
    """The app's engine as DB_TRANSACTION_POOLER=true builds it."""
    engine = create_async_engine(pgbouncer_url, **engine_options(transaction_pooler=True))
    set_timeouts_per_transaction(engine)
    yield engine
    await engine.dispose()


async def test_the_options_of_a_direct_connection_are_refused(pgbouncer_url):
    # The timeouts travel as startup parameters, which PgBouncer does not know.
    engine = create_async_engine(pgbouncer_url, **engine_options(transaction_pooler=False))
    try:
        with pytest.raises(Exception, match="unsupported startup parameter"):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def test_a_cached_statement_breaks_on_the_next_server_connection(pgbouncer_url):
    # The negative control of the next tests. A statement prepared and cached in one
    # transaction is executed in a later one, which the pooler serves from the other
    # server connection while the first is busy: the statement does not exist there.
    options = engine_options(transaction_pooler=False)
    del options["connect_args"]["server_settings"]
    client, blocker = (
        create_async_engine(pgbouncer_url, **options),
        create_async_engine(pgbouncer_url, **options),
    )
    query = text("SELECT CAST(:n AS integer)")
    try:
        async with client.connect() as conn:
            await conn.execute(query, {"n": 1})
            await conn.commit()
            async with blocker.connect() as busy:
                await busy.execute(text("SELECT 1"))  # holds a server connection
                with pytest.raises(DBAPIError, match="prepared statement"):
                    await conn.execute(query, {"n": 2})
    finally:
        await client.dispose()
        await blocker.dispose()


async def test_with_the_pooler_options_concurrent_sessions_work(pooled_engine, sample_table):
    sessions = async_sessionmaker(pooled_engine, expire_on_commit=False)

    async def work(n: int) -> int:
        async with sessions() as session:
            repo = SampleRepo(session)
            created = await repo.create(SampleORM(name=f"sample-{n}", owner_id=n))
            await session.commit()
            found = await repo.get_by_id(created.id)
            await repo.delete(found)
            await session.commit()
            return found.owner_id

    # Several rounds: the statements of a session move between the server connections.
    for _ in range(3):
        assert sorted(await asyncio.gather(*(work(n) for n in range(20)))) == list(range(20))

    # And none is left on them: named statements piled up there, a few per transaction,
    # on connections the pooler never resets.
    for _ in range(4):  # each transaction may see either server connection
        async with pooled_engine.connect() as conn:
            left = await conn.execute(text("SELECT count(*) FROM pg_prepared_statements"))
            assert left.scalar_one() == 0


async def test_the_timeouts_hold_in_every_transaction(pooled_engine):
    for _ in range(3):
        async with pooled_engine.begin() as conn:
            statement = (await conn.execute(text("SHOW statement_timeout"))).scalar_one()
            lock = (await conn.execute(text("SHOW lock_timeout"))).scalar_one()
        assert statement == f"{settings.DB_STATEMENT_TIMEOUT_MS // 1000}s"
        assert lock == f"{settings.DB_LOCK_TIMEOUT_MS // 1000}s"


async def test_a_notification_sent_through_the_pooler_reaches_a_direct_listener(
    pooled_engine, pg_url
):
    # The event bus publishes through the pool (the pooler) and listens on DB_DIRECT_URL.
    heard = asyncio.Event()
    listener = await asyncpg.connect(pg_url.replace("postgresql+asyncpg", "postgresql"))
    try:
        await listener.add_listener(CHANNEL, lambda *_: heard.set())
        async with pooled_engine.begin() as conn:
            await conn.execute(text("SELECT pg_notify(:channel, 'x')"), {"channel": CHANNEL})
        await asyncio.wait_for(heard.wait(), timeout=5)
    finally:
        await listener.close()
