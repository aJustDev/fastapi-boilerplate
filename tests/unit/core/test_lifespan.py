"""Startup does not depend on the database answering at that moment."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI

from app.core import lifespan as lifespan_module
from app.core.lifespan import lifespan


@pytest.fixture
def workers():
    outbox, jobs = MagicMock(), MagicMock()
    for worker in (outbox, jobs):
        worker.start, worker.stop = AsyncMock(), AsyncMock()
    with (
        patch.object(lifespan_module, "OutboxWorker", return_value=outbox),
        patch.object(lifespan_module, "JobWorker", return_value=jobs),
        patch.object(lifespan_module, "check_utc_timezone"),
        patch.object(lifespan_module, "log_system_info", new_callable=AsyncMock) as banner,
        patch.object(lifespan_module, "engine", MagicMock(dispose=AsyncMock())),
    ):
        yield outbox, jobs, banner


@pytest.mark.parametrize("db_status", ["OK", "UNAVAILABLE"])
async def test_workers_start_and_the_instance_is_ready_whatever_the_database_says(
    workers, db_status: str
):
    # A database that is down at startup comes back; an instance that gave up at startup
    # would stay alive, out of rotation and without workers until someone restarts it.
    outbox, jobs, _ = workers
    app = FastAPI()

    with patch.object(lifespan_module, "check_database", AsyncMock(return_value=db_status)):
        async with lifespan(app):
            outbox.start.assert_awaited_once()
            jobs.start.assert_awaited_once()
            assert app.state.ready is True

    assert app.state.ready is False
    outbox.stop.assert_awaited_once()
    jobs.stop.assert_awaited_once()


async def test_the_banner_says_the_workers_are_waiting_for_the_database(workers):
    _, _, banner = workers

    with patch.object(lifespan_module, "check_database", AsyncMock(return_value="UNAVAILABLE")):
        async with lifespan(FastAPI()):
            pass

    assert banner.call_args.kwargs["outbox_status"] == "waiting for the database"
    assert banner.call_args.kwargs["jobs_status"] == "waiting for the database"


async def test_workers_can_be_left_to_another_process(workers, monkeypatch):
    outbox, jobs, banner = workers
    monkeypatch.setattr(lifespan_module.settings, "OUTBOX_WORKER_ENABLED", False)
    monkeypatch.setattr(lifespan_module.settings, "JOB_WORKER_ENABLED", False)

    with patch.object(lifespan_module, "check_database", AsyncMock(return_value="OK")):
        async with lifespan(FastAPI()):
            outbox.start.assert_not_awaited()
            jobs.start.assert_not_awaited()

    assert banner.call_args.kwargs["outbox_status"] == "disabled"
    assert banner.call_args.kwargs["jobs_status"] == "disabled"
