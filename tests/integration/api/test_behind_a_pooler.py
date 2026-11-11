"""The whole app behind a pooler in transaction mode, as DB_TRANSACTION_POOLER=true builds it.

The flows that hold a row lock and write events, through a pooler that lends a different
server connection to each transaction.
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.db import async_session_factory, engine_options, set_timeouts_per_transaction
from app.core.db import engine as app_engine
from main import app
from tests.integration.api.helpers import signed_up
from tests.integration.api.workshops import enroll, get_workshop, published_workshop

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(loop_scope="session")
async def pooled_client(pgbouncer_url, async_engine) -> AsyncGenerator[AsyncClient]:
    engine = create_async_engine(pgbouncer_url, **engine_options(transaction_pooler=True))
    set_timeouts_per_transaction(engine)
    async_session_factory.configure(bind=engine)
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        async_session_factory.configure(bind=app_engine)
        await engine.dispose()
        async with async_engine.begin() as conn:
            await conn.execute(
                text("TRUNCATE users, workshops, outbox_events RESTART IDENTITY CASCADE")
            )


async def test_a_workshop_fills_through_the_pooler(pooled_client: AsyncClient):
    organizer = await signed_up(pooled_client, "organizer")
    attendee = await signed_up(pooled_client, "attendee")
    workshop = await published_workshop(pooled_client, organizer, capacity=1)

    first = await enroll(pooled_client, attendee, workshop["id"])
    again = await enroll(pooled_client, attendee, workshop["id"])

    assert (first.status_code, again.status_code) == (201, 200)
    assert (await get_workshop(pooled_client, organizer, workshop["id"]))["seats_taken"] == 1
