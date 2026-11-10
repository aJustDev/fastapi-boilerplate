"""Tell the outside world what happened to an enrollment.

Each handler is registered with @dispatcher.register and run by the outbox worker. A
handler that raises is retried with backoff; one that returns is never run again for
that event. Delivery is at least once, so the receiver gets the event id to recognise a
repeat.
"""

import logging
import uuid

import httpx

from app.core.config import settings
from app.core.events.dispatcher import dispatcher

logger = logging.getLogger(__name__)


async def _deliver(event_type: str, payload: dict, event_id: uuid.UUID) -> None:
    """POST the event to WEBHOOK_URL, if one is configured.

    Anything but a 2xx raises: an answer is not a delivery, and returning here would mark
    the handler as done for good. The event id travels as Idempotency-Key because the
    receiver may get the same event twice (a retry after a timeout it did process).
    """
    if not settings.WEBHOOK_URL:
        logger.debug("[%s] WEBHOOK_URL not configured, skipping", event_type)
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.WEBHOOK_URL,
            json={"event": event_type, "id": str(event_id), "payload": payload},
            headers={"Idempotency-Key": str(event_id)},
        )
    response.raise_for_status()
    logger.info("[%s] Webhook delivered (status=%d)", event_type, response.status_code)


@dispatcher.register("enrollment.confirmed")
async def notify_confirmed(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("enrollment.confirmed", payload, event_id)


@dispatcher.register("enrollment.promoted")
async def notify_promoted(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("enrollment.promoted", payload, event_id)


@dispatcher.register("enrollment.cancelled")
async def notify_cancelled(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("enrollment.cancelled", payload, event_id)


@dispatcher.register("enrollment.reminder")
async def notify_reminder(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("enrollment.reminder", payload, event_id)
