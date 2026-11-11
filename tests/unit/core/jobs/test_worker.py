import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.dialects import postgresql

from app.core.jobs.worker import JobWorker


def _session_factory(*sessions: AsyncMock) -> MagicMock:
    """async_session_factory stand-in that hands out the given sessions in order."""
    contexts = []
    for session in sessions:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        contexts.append(ctx)
    return MagicMock(side_effect=contexts)


def _claim_session(row: tuple[str, int] | None) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.one_or_none.return_value = row
    session.execute = AsyncMock(return_value=result)
    return session


def _values(session: AsyncMock) -> dict:
    """Bound values of the single UPDATE executed on *session*."""
    stmt = session.execute.call_args.args[0]
    return stmt.compile(dialect=postgresql.dialect()).params


class TestExecuteJob:
    async def test_successful_execution(self):
        worker = JobWorker()
        claim = _claim_session(("test_job", 300))
        reschedule = AsyncMock()
        handler = AsyncMock()

        with (
            patch(
                "app.core.jobs.worker.async_session_factory", _session_factory(claim, reschedule)
            ),
            patch("app.core.jobs.worker.job_registry.get", return_value=handler),
        ):
            await worker._execute_job(uuid.uuid4())

        handler.assert_called_once()
        claim.commit.assert_called_once()
        reschedule.commit.assert_called_once()
        values = _values(reschedule)
        assert values["status"] == "PENDING"
        assert values["lease_until"] is None
        assert values["last_error"] is None

    async def test_claim_sets_running_with_lease(self):
        worker = JobWorker()
        claim = _claim_session(None)

        with patch("app.core.jobs.worker.async_session_factory", _session_factory(claim)):
            await worker._execute_job(uuid.uuid4())

        values = _values(claim)
        assert values["status"] == "RUNNING"
        assert values["claimed_by"] == worker._worker_id
        assert values["lease_until"] is not None

    async def test_lost_claim_does_not_run_handler(self):
        # Another worker moved the row out of PENDING between the SELECT and the claim.
        worker = JobWorker()
        claim = _claim_session(None)
        handler = AsyncMock()

        with (
            patch("app.core.jobs.worker.async_session_factory", _session_factory(claim)),
            patch("app.core.jobs.worker.job_registry.get", return_value=handler),
        ):
            await worker._execute_job(uuid.uuid4())

        handler.assert_not_called()

    async def test_handler_failure_still_reschedules(self):
        worker = JobWorker()
        claim = _claim_session(("test_job", 300))
        reschedule = AsyncMock()
        handler = AsyncMock(side_effect=RuntimeError("boom"))

        with (
            patch(
                "app.core.jobs.worker.async_session_factory", _session_factory(claim, reschedule)
            ),
            patch("app.core.jobs.worker.job_registry.get", return_value=handler),
        ):
            await worker._execute_job(uuid.uuid4())

        values = _values(reschedule)
        assert values["status"] == "PENDING"
        assert "boom" in values["last_error"]

    async def test_no_handler_logs_warning_and_reschedules(self):
        worker = JobWorker()
        claim = _claim_session(("missing_job", 300))
        reschedule = AsyncMock()

        with (
            patch(
                "app.core.jobs.worker.async_session_factory", _session_factory(claim, reschedule)
            ),
            patch("app.core.jobs.worker.job_registry.get", return_value=None),
        ):
            await worker._execute_job(uuid.uuid4())

        values = _values(reschedule)
        assert values["status"] == "PENDING"
        assert "No handler" in values["last_error"]


class TestRecoverStaleJobs:
    async def test_only_expired_leases_are_recovered(self):
        worker = JobWorker()
        result = MagicMock()
        result.rowcount = 2
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)

        with patch("app.core.jobs.worker.async_session_factory", _session_factory(session)):
            await worker._recover_stale_jobs()

        session.commit.assert_called_once()
        sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
        assert "lease_until IS NULL" in sql
        assert "lease_until <" in sql


class TestStop:
    async def test_a_worker_that_never_started_reports_nothing(self, caplog):
        # JOB_WORKER_ENABLED=false: the lifespan still calls stop().
        with caplog.at_level("INFO", logger="app.core.jobs.worker"):
            await JobWorker().stop()
        assert "stopped" not in caplog.text


class TestTheLineOfARun:
    """One line per run: INFO when the job did something, DEBUG when it had nothing to do."""

    async def _run(self, handler: AsyncMock, caplog) -> list:
        claim, reschedule = _claim_session(("cleanup", 60)), AsyncMock()
        with (
            patch(
                "app.core.jobs.worker.async_session_factory", _session_factory(claim, reschedule)
            ),
            patch("app.core.jobs.worker.job_registry.get", return_value=handler),
            caplog.at_level("DEBUG", logger="app.core.jobs.worker"),
        ):
            await JobWorker()._execute_job(uuid.uuid4())
        return [r for r in caplog.records if r.name == "app.core.jobs.worker"]

    async def test_a_run_that_did_something_is_one_info_line(self, caplog):
        [record] = await self._run(AsyncMock(return_value="3 rows deleted"), caplog)
        assert record.levelname == "INFO"
        assert record.getMessage().startswith("Job cleanup: 3 rows deleted (")
        assert record.fields["job"]["result"] == "3 rows deleted"

    async def test_a_run_with_nothing_to_do_is_one_debug_line(self, caplog):
        [record] = await self._run(AsyncMock(return_value=None), caplog)
        assert record.levelname == "DEBUG"
        assert record.getMessage().startswith("Job cleanup: nothing to do (")

    async def test_a_failed_run_is_one_error_with_its_traceback(self, caplog):
        [record] = await self._run(AsyncMock(side_effect=RuntimeError("boom")), caplog)
        assert record.levelname == "ERROR"
        assert record.getMessage() == "Job cleanup failed"
        assert record.exc_info is not None
