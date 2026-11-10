"""Job worker against real PostgreSQL: each due job runs once, crashed claims come back."""

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.jobs import worker as worker_module
from app.core.jobs.models import ScheduledJobORM
from app.core.jobs.registry import job_registry
from app.core.jobs.worker import JobWorker

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def committing_tables() -> list[str]:
    return ["scheduled_jobs"]


@pytest.fixture
def isolated_registry():
    """Jobs registered by a test disappear when it ends."""
    snapshot = dict(job_registry._jobs)
    yield job_registry
    job_registry._jobs.clear()
    job_registry._jobs.update(snapshot)


@pytest_asyncio.fixture(loop_scope="session")
async def factory(committing_factory, monkeypatch):
    monkeypatch.setattr(worker_module, "async_session_factory", committing_factory)
    return committing_factory


async def _seed(factory, **fields) -> None:
    async with factory() as session:
        session.add(ScheduledJobORM(**fields))
        await session.commit()


async def _drain(worker: JobWorker) -> None:
    """What the real loop does: process due jobs, wait a little, repeat."""
    for _ in range(30):
        await worker._process_due_jobs()
        await asyncio.sleep(0.01)


async def test_each_due_job_runs_once_with_several_workers(factory, isolated_registry):
    ran: list[str] = []
    names = [f"job_{n}" for n in range(8)]

    for name in names:

        @isolated_registry.register(name)
        async def handler(name: str = name) -> None:
            ran.append(name)
            await asyncio.sleep(0.02)  # widen the window between claim and reschedule

        await _seed(
            factory,
            job_name=name,
            interval_seconds=3600,
            next_run_at=datetime.now(UTC) - timedelta(seconds=1),
        )

    await asyncio.gather(*(_drain(JobWorker()) for _ in range(4)))

    assert Counter(ran) == Counter(names)
    async with factory() as session:
        jobs = (await session.execute(select(ScheduledJobORM))).scalars().all()
    assert {job.status for job in jobs} == {"PENDING"}
    assert {job.run_count for job in jobs} == {1}


async def test_running_job_with_expired_lease_is_recovered(factory):
    # The worker that claimed it died: nobody will ever reschedule it.
    await _seed(
        factory,
        job_name="orphan",
        interval_seconds=60,
        status="RUNNING",
        claimed_by="dead-host:1",
        lease_until=datetime.now(UTC) - timedelta(seconds=1),
    )

    await JobWorker()._recover_stale_jobs()

    async with factory() as session:
        job = (await session.execute(select(ScheduledJobORM))).scalars().one()
    assert job.status == "PENDING"
    assert job.claimed_by is None
    assert job.lease_until is None


async def test_running_job_with_valid_lease_is_left_alone(factory):
    # Another worker is running it right now: taking it back would run it twice.
    await _seed(
        factory,
        job_name="busy",
        interval_seconds=60,
        status="RUNNING",
        claimed_by="other-host:2",
        lease_until=datetime.now(UTC) + timedelta(seconds=60),
    )

    await JobWorker()._recover_stale_jobs()

    async with factory() as session:
        job = (await session.execute(select(ScheduledJobORM))).scalars().one()
    assert job.status == "RUNNING"
    assert job.claimed_by == "other-host:2"
