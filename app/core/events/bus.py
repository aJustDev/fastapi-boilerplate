import logging
from collections.abc import Iterable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events.models import OutboxEventORM
from app.core.logging.context import get_request_id

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
        aggregate_id: str | int | None = None,
        correlation_id: str | None = None,
    ) -> OutboxEventORM:
        """Insert an event into the outbox within the current transaction.

        Does NOT commit — the caller's session lifecycle handles that. The NOTIFY wakes
        the outbox workers when the transaction commits.

        `aggregate_id` is the id of the entity the event is about. `correlation_id`
        defaults to the id of the current request, so the handlers log under it.
        """
        event = OutboxEventORM(
            event_type=event_type,
            payload=payload,
            aggregate_id=None if aggregate_id is None else str(aggregate_id),
            correlation_id=correlation_id or get_request_id() or None,
            max_retries=settings.OUTBOX_MAX_RETRIES,
        )
        self.session.add(event)
        await self.session.flush()
        await self.session.refresh(event)

        await self._notify(str(event.id))
        # DEBUG: the line that matters is the worker's, once it is processed.
        logger.debug("Published %s %s", event_type, event.id)
        return event

    async def publish_many(
        self,
        event_type: str,
        events: Iterable[tuple[str | int | None, dict[str, Any]]],
    ) -> int:
        """Insert one event per `(aggregate_id, payload)` pair; returns how many.

        For a change that concerns many recipients (a cancellation, a batch of
        reminders): each one gets its own event, so each delivery is retried on its own
        and carries its own id. The rows go in one batch and a single NOTIFY wakes the
        workers, whatever the number.
        """
        correlation_id = get_request_id() or None
        rows = [
            OutboxEventORM(
                event_type=event_type,
                payload=payload,
                aggregate_id=None if aggregate_id is None else str(aggregate_id),
                correlation_id=correlation_id,
                max_retries=settings.OUTBOX_MAX_RETRIES,
            )
            for aggregate_id, payload in events
        ]
        if not rows:
            return 0
        self.session.add_all(rows)
        await self.session.flush()
        await self._notify(event_type)
        logger.debug("Published %d %s events", len(rows), event_type)
        return len(rows)

    async def _notify(self, payload: str) -> None:
        # The payload is only for whoever reads the logs: a worker wakes up and claims
        # whatever is pending.
        await self.session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {"channel": CHANNEL, "payload": payload},
        )
