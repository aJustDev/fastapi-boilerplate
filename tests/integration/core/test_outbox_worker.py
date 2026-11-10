"""Outbox worker against real PostgreSQL: delivery guarantees with several workers."""

import asyncio
from collections import Counter

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.events import worker as worker_module
from app.core.events.bus import EventBus
from app.core.events.dispatcher import dispatcher
from app.core.events.models import OutboxEventORM
from app.core.events.worker import OutboxWorker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def committing_tables() -> list[str]:
    return ["outbox_events"]


@pytest.fixture
def isolated_dispatcher():
    """Handlers registered by a test disappear when it ends."""
    snapshot = {k: list(v) for k, v in dispatcher._handlers.items()}
    yield dispatcher
    dispatcher._handlers.clear()
    dispatcher._handlers.update(snapshot)


@pytest_asyncio.fixture(loop_scope="session")
async def factory(committing_factory, monkeypatch):
    monkeypatch.setattr(worker_module, "async_session_factory", committing_factory)
    return committing_factory


async def _publish(factory, event_type: str, count: int) -> None:
    async with factory() as session:
        bus = EventBus(session)
        for n in range(count):
            await bus.publish(event_type, {"n": n})
        await session.commit()


async def _drain(worker: OutboxWorker) -> None:
    """What the real loop does: process a batch, wait a little, repeat."""
    for _ in range(40):
        await worker._process_batch()
        await asyncio.sleep(0.01)


async def test_each_event_is_dispatched_once_with_several_workers(factory, isolated_dispatcher):
    handled: list[int] = []

    @isolated_dispatcher.register("test.concurrent")
    async def record(payload: dict) -> None:
        handled.append(payload["n"])
        await asyncio.sleep(0.02)  # widen the window in which locks are held

    await _publish(factory, "test.concurrent", 20)

    await asyncio.gather(*(_drain(OutboxWorker()) for _ in range(4)))

    assert Counter(handled) == Counter(range(20))
    async with factory() as session:
        statuses = (await session.execute(select(OutboxEventORM.status))).scalars().all()
    assert set(statuses) == {"PROCESSED"}


async def test_event_without_handlers_is_retried_not_processed(factory, isolated_dispatcher):
    await _publish(factory, "test.nobody_listens", 1)

    await OutboxWorker()._process_batch()

    async with factory() as session:
        event = (await session.execute(select(OutboxEventORM))).scalars().one()
    assert event.status == "PENDING"
    assert event.retry_count == 1
    assert "no handlers" in event.last_error


async def test_notify_wakes_the_worker_before_the_poll_interval(
    factory, isolated_dispatcher, pg_url, monkeypatch
):
    handled = asyncio.Event()

    @isolated_dispatcher.register("test.notify")
    async def record(payload: dict) -> None:
        handled.set()

    dsn = pg_url.replace("postgresql+asyncpg://", "postgresql://")
    monkeypatch.setattr(worker_module, "build_asyncpg_dsn", lambda: dsn)
    monkeypatch.setattr(worker_module.settings, "OUTBOX_POLL_INTERVAL_SECONDS", 60)

    worker = OutboxWorker()
    await worker.start()
    try:
        await _wait_for_listener(factory)
        await _publish(factory, "test.notify", 1)
        # Far below the 60 s poll: only the NOTIFY can explain it.
        await asyncio.wait_for(handled.wait(), timeout=5)
    finally:
        await worker.stop()


async def _wait_for_listener(factory) -> None:
    """Wait until the worker's LISTEN connection is open, or the NOTIFY could be lost."""
    for _ in range(100):
        async with factory() as session:
            listening = (
                await session.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE query LIKE 'LISTEN%'")
                )
            ).scalar_one()
        if listening:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("outbox worker never started listening")
