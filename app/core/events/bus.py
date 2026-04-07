import logging
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events.outbox import OutboxEventORM

logger = logging.getLogger(__name__)

CHANNEL = "outbox_event_channel"


class EventBus:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        aggregate_id: uuid.UUID | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> OutboxEventORM:
        """Insert an event into the outbox within the current transaction.

        Does NOT commit — the caller's session lifecycle handles that.
        Sends a NOTIFY with the event id for worker debugging.
        """
        event = OutboxEventORM(
            event_type=event_type,
            payload=payload,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)

        await self.session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": CHANNEL, "payload": str(event.id)},
        )
        logger.info("Published event %s (id=%s)", event_type, event.id)
        return event
