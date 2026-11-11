import asyncio
import contextlib
import logging
import random
from datetime import UTC, datetime, timedelta

import asyncpg
import sqlalchemy.exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.db import async_session_factory, build_asyncpg_dsn
from app.core.events.dispatcher import dispatcher
from app.core.events.models import OutboxEventORM
from app.core.logging.context import request_id_var
from app.core.logging.errors import one_line
from app.core.metrics.instruments import outbox_events_failed_total, outbox_events_processed_total

logger = logging.getLogger(__name__)

CHANNEL = "outbox_event_channel"
BATCH_SIZE = 50
MAX_BACKOFF_HOURS = 1
MAX_RECONNECT_DELAY = 60

# A database that does not answer, or answers that it cannot take connections yet: the
# worker retries on its own, so each attempt is one line, without a traceback.
_CONNECTION_ERRORS = (
    OSError,
    TimeoutError,
    asyncpg.PostgresConnectionError,
    asyncpg.CannotConnectNowError,
    asyncpg.InterfaceError,
    sqlalchemy.exc.OperationalError,
    sqlalchemy.exc.InterfaceError,
)


class OutboxWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()
        self._wake_event = asyncio.Event()

    async def start(self) -> None:
        self._shutdown_event.clear()
        self._wake_event.clear()
        self._task = asyncio.create_task(self._run(), name="outbox-worker")
        logger.debug("Outbox worker started")

    async def stop(self) -> None:
        self._shutdown_event.set()
        if self._task is None:  # never started (disabled): nothing to stop or to report
            return
        if not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        logger.info("Outbox worker stopped")

    # ── Main loop ─────────────────────────────────────────

    async def _run(self) -> None:
        reconnect_attempt = 0

        while not self._shutdown_event.is_set():
            conn: asyncpg.Connection | None = None
            try:
                conn = await asyncpg.connect(
                    build_asyncpg_dsn(), timeout=settings.DB_CONNECT_TIMEOUT
                )
                await conn.add_listener(CHANNEL, self._on_notify)
                reconnect_attempt = 0

                while not self._shutdown_event.is_set():
                    # Woken up by NOTIFY; the poll timeout is the fallback
                    # for notifications lost while the listener was reconnecting.
                    with contextlib.suppress(TimeoutError):
                        await asyncio.wait_for(
                            self._wake_event.wait(),
                            timeout=settings.OUTBOX_POLL_INTERVAL_SECONDS,
                        )
                    # Clear before processing: a NOTIFY that arrives during the batch
                    # triggers another round instead of being lost.
                    self._wake_event.clear()
                    if self._shutdown_event.is_set():
                        break

                    # Heartbeat: verify connection is alive
                    try:
                        await conn.execute("SELECT 1")
                    except _CONNECTION_ERRORS as exc:
                        logger.warning(
                            "Outbox listener lost its connection (%s), reconnecting",
                            one_line(exc),
                        )
                        break

                    await self._process_batch()

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                reconnect_attempt += 1
                delay = min(2**reconnect_attempt, MAX_RECONNECT_DELAY)
                if isinstance(exc, _CONNECTION_ERRORS):
                    logger.warning(
                        "Outbox worker cannot reach the database (%s), retrying in %ds",
                        one_line(exc),
                        delay,
                    )
                else:
                    logger.exception("Outbox worker error, retrying in %ds", delay)
                await asyncio.sleep(delay)
            finally:
                if conn and not conn.is_closed():
                    with contextlib.suppress(Exception):
                        await conn.remove_listener(CHANNEL, self._on_notify)
                    await conn.close()

    def _on_notify(
        self,
        connection: asyncpg.Connection,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """Callback for LISTEN notifications. Triggers batch processing."""
        logger.debug("Received NOTIFY on %s: %s", channel, payload)
        self._wake_event.set()

    # ── Batch processing ──────────────────────────────────

    async def _process_batch(self) -> None:
        # One event per transaction: the FOR UPDATE SKIP LOCKED lock lives until the
        # commit of THAT event. Locking the whole batch and committing inside the loop
        # released the locks of the rows still pending after the first commit, and a
        # second worker (--workers N, replicas, rolling deploy) dispatched them again.
        for _ in range(BATCH_SIZE):
            async with async_session_factory() as session:
                stmt = (
                    select(OutboxEventORM)
                    .where(OutboxEventORM.status == "PENDING")
                    .where(OutboxEventORM.scheduled_at <= datetime.now(UTC))
                    .order_by(OutboxEventORM.scheduled_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                )
                event = (await session.execute(stmt)).scalars().first()
                if event is None:
                    return
                await self._handle_event(session, event)
                await session.commit()

    async def _handle_event(
        self,
        session: AsyncSession,
        event: OutboxEventORM,
    ) -> None:
        # The handlers, and the lines of this event, log under the request id of the
        # request that published it.
        token = request_id_var.set(event.correlation_id or "")
        try:
            await self._dispatch_and_record(session, event)
        finally:
            request_id_var.reset(token)

    async def _dispatch_and_record(self, session: AsyncSession, event: OutboxEventORM) -> None:
        # Build set of handlers that already succeeded (from previous retries)
        completed = {
            name for name, info in (event.handler_state or {}).items() if info.get("status") == "ok"
        }

        dispatch_result = await dispatcher.dispatch(
            event.event_type,
            event.payload,
            event_id=event.id,
            completed_handlers=completed,
        )

        # Merge per-handler results into handler_state
        new_state = dict(event.handler_state or {})
        now_iso = datetime.now(UTC).isoformat()
        for r in dispatch_result.results:
            if r.skipped:
                continue
            entry: dict[str, str] = {"status": "ok" if r.success else "failed", "at": now_iso}
            if r.error:
                entry["error"] = r.error[:500]
            new_state[r.handler_name] = entry
        event.handler_state = new_state
        flag_modified(event, "handler_state")

        if dispatch_result.all_succeeded:
            event.status = "PROCESSED"
            event.processed_at = datetime.now(UTC)
            outbox_events_processed_total.labels(event_type=event.event_type).inc()
            logger.info("Processed %s %s", event.event_type, event.id)
        else:
            event.retry_count += 1
            event.last_error = dispatch_result.errors_summary

            if event.retry_count >= event.max_retries:
                event.status = "FAILED"
                outbox_events_failed_total.labels(event_type=event.event_type).inc()
                logger.critical(
                    "Gave up on %s %s after %d attempts: %s; `python -m app.cli outbox replay` "
                    "retries it",
                    event.event_type,
                    event.id,
                    event.retry_count,
                    dispatch_result.failures,
                    exc_info=dispatch_result.bug,
                )
            else:
                # Exponential backoff with jitter and cap
                backoff_seconds = min(
                    2**event.retry_count + random.uniform(0, 5),  # noqa: S311 -- jitter, not crypto
                    MAX_BACKOFF_HOURS * 3600,
                )
                event.scheduled_at = datetime.now(UTC) + timedelta(
                    seconds=backoff_seconds,
                )
                # The traceback of a bug goes with the first failure, to debug it without
                # waiting for the last attempt, and with the last; the ones between are one
                # line each, like every attempt of a failure the handler could name.
                first = event.retry_count == 1
                logger.warning(
                    "Retry %d/%d of %s %s in %.0fs: %s",
                    event.retry_count,
                    event.max_retries,
                    event.event_type,
                    event.id,
                    backoff_seconds,
                    dispatch_result.failures,
                    exc_info=dispatch_result.bug if first else None,
                )

        await session.flush()
