import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.jobs.worker import JobWorker
from app.models.jobs.scheduled_job import ScheduledJobORM


def _make_job(
    *,
    job_name: str = "test_job",
    interval_seconds: int = 300,
    status: str = "PENDING",
    run_count: int = 0,
) -> ScheduledJobORM:
    job = ScheduledJobORM(
        id=uuid.uuid4(),
        job_name=job_name,
        interval_seconds=interval_seconds,
        status=status,
        next_run_at=datetime.now(UTC) - timedelta(seconds=10),
        run_count=run_count,
        created_at=datetime.now(UTC),
    )
    return job


class TestExecuteJob:
    async def test_successful_execution(self):
        worker = JobWorker()
        session = AsyncMock()
        job = _make_job()

        handler = AsyncMock()

        with patch(
            "app.core.jobs.worker.job_registry.get",
            return_value=handler,
        ):
            await worker._execute_job(session, job)

        handler.assert_called_once()
        assert job.status == "PENDING"
        assert job.run_count == 1
        assert job.last_run_at is not None
        assert job.last_error is None
        assert job.claimed_by == worker._worker_id
        # next_run_at should be ~300s in the future
        assert job.next_run_at > datetime.now(UTC) + timedelta(seconds=290)
        assert session.commit.call_count == 2  # claim + reschedule

    async def test_handler_failure_still_reschedules(self):
        worker = JobWorker()
        session = AsyncMock()
        job = _make_job()

        handler = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "app.core.jobs.worker.job_registry.get",
            return_value=handler,
        ):
            await worker._execute_job(session, job)

        assert job.status == "PENDING"
        assert job.run_count == 1
        assert job.last_error is not None
        assert "boom" in job.last_error
        assert job.next_run_at > datetime.now(UTC) + timedelta(seconds=290)

    async def test_no_handler_logs_warning_and_reschedules(self):
        worker = JobWorker()
        session = AsyncMock()
        job = _make_job()

        with patch(
            "app.core.jobs.worker.job_registry.get",
            return_value=None,
        ):
            await worker._execute_job(session, job)

        assert job.status == "PENDING"
        assert job.run_count == 1
        assert job.last_error is not None
        assert "No handler" in job.last_error

    async def test_claim_sets_running_status(self):
        worker = JobWorker()
        session = AsyncMock()
        job = _make_job()

        statuses_at_commit: list[str] = []

        async def track_commit():
            statuses_at_commit.append(job.status)

        session.commit = AsyncMock(side_effect=track_commit)

        handler = AsyncMock()

        with patch(
            "app.core.jobs.worker.job_registry.get",
            return_value=handler,
        ):
            await worker._execute_job(session, job)

        # First commit should be RUNNING (claim), second should be PENDING (reschedule)
        assert statuses_at_commit[0] == "RUNNING"
        assert statuses_at_commit[1] == "PENDING"


class TestRecoverStaleJobs:
    async def test_resets_running_to_pending(self):
        worker = JobWorker()

        mock_result = MagicMock()
        mock_result.rowcount = 2

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = AsyncMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.jobs.worker.async_session_factory",
            return_value=mock_factory,
        ):
            await worker._recover_stale_jobs()

        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()
