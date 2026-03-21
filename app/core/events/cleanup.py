import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update

from app.core.config import settings
from app.core.db import async_session_factory
from app.models.events.outbox import OutboxEventORM

logger = logging.getLogger(__name__)


async def cleanup_processed_events(days: int | None = None) -> int:
    """Delete PROCESSED events older than ``days`` days in batches.

    Returns the total number of deleted events.
    """
    retention_days = days or settings.OUTBOX_CLEANUP_DAYS
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    total_deleted = 0

    async with async_session_factory() as session:
        while True:
            subq = (
                select(OutboxEventORM.id)
                .where(OutboxEventORM.status == "PROCESSED")
                .where(OutboxEventORM.processed_at < cutoff)
                .limit(settings.OUTBOX_CLEANUP_BATCH_SIZE)
            )
            stmt = delete(OutboxEventORM).where(OutboxEventORM.id.in_(subq))
            result = await session.execute(stmt)
            await session.commit()

            deleted = result.rowcount
            total_deleted += deleted

            if deleted < settings.OUTBOX_CLEANUP_BATCH_SIZE:
                break

    logger.info(
        "Cleaned up %d processed outbox events older than %d days",
        total_deleted,
        retention_days,
    )
    return total_deleted


async def replay_failed_events(
    event_ids: list[uuid.UUID] | None = None,
    *,
    reset_handler_state: bool = False,
) -> int:
    """Reset FAILED events back to PENDING for reprocessing.

    If ``event_ids`` is provided, only those events are replayed.
    Otherwise, all FAILED events are replayed.

    When ``reset_handler_state`` is True, the per-handler execution state
    is cleared so that **all** handlers re-execute (useful when a handler
    fix has been deployed and previous successes should be re-run).

    Returns the number of events replayed.
    """
    async with async_session_factory() as session:
        values: dict = {
            "status": "PENDING",
            "retry_count": 0,
            "scheduled_at": datetime.now(UTC),
            "last_error": None,
        }
        if reset_handler_state:
            values["handler_state"] = {}

        stmt = update(OutboxEventORM).where(OutboxEventORM.status == "FAILED").values(**values)

        if event_ids is not None:
            stmt = stmt.where(OutboxEventORM.id.in_(event_ids))

        result = await session.execute(stmt)
        await session.commit()

        count = result.rowcount
        logger.info("Replayed %d failed outbox events", count)
        return count
