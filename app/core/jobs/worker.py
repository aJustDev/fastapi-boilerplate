import asyncio
import contextlib
import logging
import os
import socket
import traceback
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.core.config import settings
from app.core.db import async_session_factory
from app.core.jobs.registry import job_registry
from app.models.jobs.scheduled_job import ScheduledJobORM

logger = logging.getLogger(__name__)

BATCH_SIZE = 10


class JobWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._worker_id = f"{socket.gethostname()}:{os.getpid()}"

    async def start(self) -> None:
        self._shutdown_event.clear()
        self._task = asyncio.create_task(self._run(), name="job-worker")
        logger.debug("Job worker started (id=%s)", self._worker_id)

    async def stop(self) -> None:
        self._shutdown_event.set()
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Job worker stopped")

    # ── Main loop ─────────────────────────────────────────

    async def _run(self) -> None:
        await self._recover_stale_jobs()

        while not self._shutdown_event.is_set():
            try:
                await self._process_due_jobs()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Job worker error")

            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=settings.JOB_POLL_INTERVAL_SECONDS,
                )
                break
            except TimeoutError:
                pass

    # ── Stale recovery ────────────────────────────────────

    async def _recover_stale_jobs(self) -> None:
        async with async_session_factory() as session:
            stmt = (
                update(ScheduledJobORM)
                .where(ScheduledJobORM.status == "RUNNING")
                .values(status="PENDING")
            )
            result = await session.execute(stmt)
            await session.commit()
            if result.rowcount:
                logger.warning("Recovered %d stale RUNNING jobs", result.rowcount)

    # ── Job processing ────────────────────────────────────

    async def _process_due_jobs(self) -> None:
        async with async_session_factory() as session:
            stmt = (
                select(ScheduledJobORM)
                .where(ScheduledJobORM.status == "PENDING")
                .where(ScheduledJobORM.next_run_at <= datetime.now(UTC))
                .order_by(ScheduledJobORM.next_run_at)
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(stmt)
            jobs = list(result.scalars().all())

            if not jobs:
                return

            for job in jobs:
                await self._execute_job(session, job)

    async def _execute_job(
        self,
        session: "asyncio.AbstractEventLoop",
        job: ScheduledJobORM,
    ) -> None:
        # Phase 1: claim the job
        job.status = "RUNNING"
        job.claimed_by = self._worker_id
        job.updated_at = datetime.now(UTC)
        await session.commit()

        # Phase 2: execute the handler
        handler = job_registry.get(job.job_name)
        error: str | None = None

        if handler is None:
            error = f"No handler registered for job '{job.job_name}'"
            logger.warning(error)
        else:
            start = datetime.now(UTC)
            try:
                await asyncio.wait_for(
                    handler(),
                    timeout=settings.JOB_HANDLER_TIMEOUT_SECONDS,
                )
                elapsed_ms = (datetime.now(UTC) - start).total_seconds() * 1000
                logger.info(
                    "Job '%s' done (%.0fms, PID=%d)",
                    job.job_name,
                    elapsed_ms,
                    os.getpid(),
                )
            except Exception:
                error = traceback.format_exc()
                logger.exception("Job '%s' failed (PID=%d)", job.job_name, os.getpid())

        # Phase 3: reschedule
        job.status = "PENDING"
        job.next_run_at = datetime.now(UTC) + timedelta(seconds=job.interval_seconds)
        job.last_run_at = datetime.now(UTC)
        job.run_count += 1
        job.last_error = error[:500] if error else None
        job.updated_at = datetime.now(UTC)
        await session.commit()
