import asyncio
import contextlib
import logging
import random
from datetime import UTC, datetime, timedelta

import asyncpg
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.config import settings
from app.core.db import async_session_factory, build_asyncpg_dsn
from app.core.events.dispatcher import dispatcher
from app.core.events.models import OutboxEventORM

logger = logging.getLogger(__name__)

CHANNEL = "outbox_event_channel"
BATCH_SIZE = 50
MAX_BACKOFF_HOURS = 1
MAX_RECONNECT_DELAY = 60


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
        if self._task and not self._task.done():
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
                conn = await asyncpg.connect(build_asyncpg_dsn())
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
                    except Exception:
                        logger.warning("Heartbeat failed, reconnecting...", exc_info=True)
                        break

                    await self._process_batch()

            except asyncio.CancelledError:
                raise
            except Exception:
                reconnect_attempt += 1
                delay = min(2**reconnect_attempt, MAX_RECONNECT_DELAY)
                logger.exception(
                    "Outbox worker connection error, retrying in %ds",
                    delay,
                )
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
        # Build set of handlers that already succeeded (from previous retries)
        completed = {
            name for name, info in (event.handler_state or {}).items() if info.get("status") == "ok"
        }

        dispatch_result = await dispatcher.dispatch(
            event.event_type,
            event.payload,
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
            logger.info(
                "Event %s processed (type=%s)",
                event.id,
                event.event_type,
            )
        else:
            event.retry_count += 1
            event.last_error = dispatch_result.errors_summary

            if event.retry_count >= event.max_retries:
                event.status = "FAILED"
                logger.critical(
                    "Event %s FAILED after %d retries (type=%s): %s",
                    event.id,
                    event.retry_count,
                    event.event_type,
                    dispatch_result.errors_summary[:500],
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
                logger.warning(
                    "Event %s retry %d/%d scheduled at %s (type=%s)",
                    event.id,
                    event.retry_count,
                    event.max_retries,
                    event.scheduled_at,
                    event.event_type,
                )

        await session.flush()
