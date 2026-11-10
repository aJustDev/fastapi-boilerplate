"""Item event handlers.

Each handler is registered via @dispatcher.register and executed by the outbox worker
when the corresponding event type is processed. A handler that raises is retried with
backoff; one that returns is never run again for that event.
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


# ── item.created ──────────────────────────────────────────


@dispatcher.register("item.created")
async def log_item_created(payload: dict, event_id: uuid.UUID) -> None:
    """Always succeeds — basic audit log."""
    logger.info(
        "[item.created] id=%s name=%s owner=%s",
        payload.get("item_id"),
        payload.get("name"),
        payload.get("owner_id"),
    )


@dispatcher.register("item.created")
async def webhook_item_created(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("item.created", payload, event_id)


# ── item.updated ──────────────────────────────────────────


@dispatcher.register("item.updated")
async def log_item_updated(payload: dict, event_id: uuid.UUID) -> None:
    logger.info(
        "[item.updated] id=%s changes=%s",
        payload.get("item_id"),
        payload.get("changes"),
    )


@dispatcher.register("item.updated")
async def webhook_item_updated(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("item.updated", payload, event_id)


# ── item.deleted ──────────────────────────────────────────


@dispatcher.register("item.deleted")
async def log_item_deleted(payload: dict, event_id: uuid.UUID) -> None:
    logger.info("[item.deleted] id=%s", payload.get("item_id"))


@dispatcher.register("item.deleted")
async def webhook_item_deleted(payload: dict, event_id: uuid.UUID) -> None:
    await _deliver("item.deleted", payload, event_id)
