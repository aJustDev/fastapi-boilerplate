import asyncio
import contextlib
import logging
import os
import socket
import traceback
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update

from app.core.config import settings
from app.core.db import async_session_factory, rowcount
from app.core.jobs.models import ScheduledJobORM
from app.core.jobs.registry import job_registry

logger = logging.getLogger(__name__)

BATCH_SIZE = 10


async def job_mismatches() -> tuple[list[str], list[str]]:
    """(handlers without a row, rows without a handler).

    A job needs both: the handler registered in code and its row in `scheduled_jobs`,
    which a migration inserts. One without the other never runs, silently.
    """
    async with async_session_factory() as session:
        rows = set((await session.execute(select(ScheduledJobORM.job_name))).scalars())
    registered = set(job_registry.registered_jobs)
    return sorted(registered - rows), sorted(rows - registered)


async def log_job_mismatches() -> None:
    without_row, without_handler = await job_mismatches()
    for name in without_row:
        logger.warning(
            "Job %r is registered but has no row in scheduled_jobs: it will never run. "
            "Add the row with a migration.",
            name,
        )
    for name in without_handler:
        logger.warning(
            "scheduled_jobs has a row for %r but no handler is registered: import its "
            "module in app/db_registry.py or remove the row.",
            name,
        )


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
        rows_checked = False
        while not self._shutdown_event.is_set():
            try:
                if not rows_checked:
                    await log_job_mismatches()
                    rows_checked = True
                await self._recover_stale_jobs()
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
    # Frees RUNNING rows whose lease expired (the worker that claimed them died).
    # A row with a valid lease belongs to a worker that is still running it.

    async def _recover_stale_jobs(self) -> None:
        async with async_session_factory() as session:
            stmt = (
                update(ScheduledJobORM)
                .where(ScheduledJobORM.status == "RUNNING")
                .where(
                    or_(
                        ScheduledJobORM.lease_until.is_(None),
                        ScheduledJobORM.lease_until < datetime.now(UTC),
                    )
                )
                .values(status="PENDING", claimed_by=None, lease_until=None)
            )
            recovered = rowcount(await session.execute(stmt))
            await session.commit()
            if recovered:
                logger.warning("Recovered %d stale RUNNING jobs", recovered)

    # ── Job processing ────────────────────────────────────
    # Lightweight SELECT of candidate ids without locks; each job is claimed
    # atomically in its own transaction by `_execute_job`.

    async def _process_due_jobs(self) -> None:
        async with async_session_factory() as session:
            stmt = (
                select(ScheduledJobORM.id)
                .where(ScheduledJobORM.status == "PENDING")
                .where(ScheduledJobORM.next_run_at <= datetime.now(UTC))
                .order_by(ScheduledJobORM.next_run_at)
                .limit(BATCH_SIZE)
            )
            candidate_ids = list((await session.execute(stmt)).scalars().all())

        for job_id in candidate_ids:
            await self._execute_job(job_id)

    async def _execute_job(self, job_id: uuid.UUID) -> None:
        # Phase 1: atomic claim. The conditional UPDATE ... RETURNING lets only one
        # worker move the row from PENDING to RUNNING; no row back means another
        # worker took it between the candidate SELECT and here.
        async with async_session_factory() as session:
            now = datetime.now(UTC)
            claim_stmt = (
                update(ScheduledJobORM)
                .where(ScheduledJobORM.id == job_id)
                .where(ScheduledJobORM.status == "PENDING")
                .where(ScheduledJobORM.next_run_at <= now)
                .values(
                    status="RUNNING",
                    claimed_by=self._worker_id,
                    lease_until=now + timedelta(seconds=settings.JOB_LEASE_SECONDS),
                    updated_at=now,
                )
                .returning(ScheduledJobORM.job_name, ScheduledJobORM.interval_seconds)
            )
            row = (await session.execute(claim_stmt)).one_or_none()
            await session.commit()
        if row is None:
            return
        job_name, interval_seconds = row

        # Phase 2: execute the handler, with no transaction open.
        handler = job_registry.get(job_name)
        error: str | None = None

        if handler is None:
            error = f"No handler registered for job '{job_name}'"
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
                    job_name,
                    elapsed_ms,
                    os.getpid(),
                )
            except Exception:
                error = traceback.format_exc()
                logger.exception("Job '%s' failed (PID=%d)", job_name, os.getpid())

        # Phase 3: reschedule. run_count is incremented in SQL to avoid lost updates.
        async with async_session_factory() as session:
            now = datetime.now(UTC)
            reschedule_stmt = (
                update(ScheduledJobORM)
                .where(ScheduledJobORM.id == job_id)
                .values(
                    status="PENDING",
                    claimed_by=None,
                    lease_until=None,
                    next_run_at=now + timedelta(seconds=interval_seconds),
                    last_run_at=now,
                    run_count=ScheduledJobORM.run_count + 1,
                    last_error=error[-500:] if error else None,
                    updated_at=now,
                )
            )
            await session.execute(reschedule_stmt)
            await session.commit()
