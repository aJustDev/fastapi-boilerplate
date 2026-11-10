"""Item event handlers.

Each handler is registered via @dispatcher.register and executed by the
outbox worker when the corresponding event type is processed.
"""

import logging

import httpx

from app.core.config import settings
from app.core.events.dispatcher import dispatcher

logger = logging.getLogger(__name__)


# ── item.created ──────────────────────────────────────────


@dispatcher.register("item.created")
async def log_item_created(payload: dict) -> None:
    """Always succeeds — basic audit log."""
    logger.info(
        "[item.created] id=%s name=%s owner=%s",
        payload.get("item_id"),
        payload.get("name"),
        payload.get("owner_id"),
    )


@dispatcher.register("item.created")
async def webhook_item_created(payload: dict) -> None:
    """Sends payload to external webhook. Skips if WEBHOOK_URL is not set."""
    if not settings.WEBHOOK_URL:
        logger.debug("[item.created] WEBHOOK_URL not configured, skipping")
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.WEBHOOK_URL,
            json={"event": "item.created", "payload": payload},
        )
    logger.info("[item.created] Webhook sent (status=%d)", response.status_code)


# ── item.updated ──────────────────────────────────────────


@dispatcher.register("item.updated")
async def log_item_updated(payload: dict) -> None:
    logger.info(
        "[item.updated] id=%s changes=%s",
        payload.get("item_id"),
        payload.get("changes"),
    )


@dispatcher.register("item.updated")
async def webhook_item_updated(payload: dict) -> None:
    if not settings.WEBHOOK_URL:
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.WEBHOOK_URL,
            json={"event": "item.updated", "payload": payload},
        )
    logger.info("[item.updated] Webhook sent (status=%d)", response.status_code)


# ── item.deleted ──────────────────────────────────────────


@dispatcher.register("item.deleted")
async def log_item_deleted(payload: dict) -> None:
    logger.info("[item.deleted] id=%s", payload.get("item_id"))


@dispatcher.register("item.deleted")
async def webhook_item_deleted(payload: dict) -> None:
    if not settings.WEBHOOK_URL:
        return

    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(
            settings.WEBHOOK_URL,
            json={"event": "item.deleted", "payload": payload},
        )
    logger.info("[item.deleted] Webhook sent (status=%d)", response.status_code)
