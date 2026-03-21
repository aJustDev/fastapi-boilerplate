# Event Bus — Transactional Outbox

## What is it?

A persistent event bus built on the **Transactional Outbox** pattern using PostgreSQL as the message broker. It decouples side effects (emails, notifications, integrations) from business logic while guaranteeing:

- **Atomicity**: If the use case fails, the event is never sent (same DB transaction).
- **Resilience**: Events are retried with exponential backoff on handler failure.
- **No external dependencies**: Uses PostgreSQL `LISTEN/NOTIFY` instead of Redis/RabbitMQ.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    HTTP Request                          │
│                         │                                │
│                    ┌────▼────┐                           │
│                    │  Router  │                           │
│                    └────┬────┘                           │
│                         │  DI: ItemService + EventBus    │
│                    ┌────▼────┐     (same AsyncSession)   │
│                    │ UseCase  │                           │
│                    └────┬────┘                           │
│               ┌─────────┼──────────┐                     │
│          ┌────▼────┐          ┌────▼─────┐               │
│          │ Service  │          │ EventBus  │              │
│          │ .create()│          │ .publish()│              │
│          └────┬────┘          └────┬─────┘               │
│               │ flush              │ flush + NOTIFY       │
│               └─────────┬──────────┘                     │
│                         │                                │
│                    get_session()                          │
│                    COMMIT (atomic)                        │
└─────────────────────────────────────────────────────────┘
                          │
                    PostgreSQL
                    NOTIFY fires
                          │
                    ┌─────▼──────┐
                    │   Worker    │  (LISTEN + poll fallback)
                    └─────┬──────┘
                          │ FOR UPDATE SKIP LOCKED
                    ┌─────▼──────┐
                    │ Dispatcher  │
                    └─────┬──────┘
                    ┌─────▼──────┐
                    │  Handlers   │  (isolated, with timeout)
                    └────────────┘
```

---

## Quick start — Publishing an event

```python
# In a use case:
from dataclasses import dataclass
from app.core.events.bus import EventBus
from app.services.orders import OrderService

@dataclass(slots=True)
class CreateOrderUseCase:
    order_service: OrderService
    event_bus: EventBus

    async def execute(self, ...) -> OrderORM:
        order = await self.order_service.create(...)

        await self.event_bus.publish(
            event_type="order.created",
            payload={"order_id": order.id, "email": order.user_email},
            aggregate_id=order.uuid,       # optional — groups events by entity
            correlation_id=request_uuid,   # optional — traces end-to-end flows
        )

        return order
        # get_session() will COMMIT both the order and the event atomically
```

In the router, inject `EventBusDep`:

```python
from typing import Annotated
from fastapi import Depends
from app.core.events.bus import EventBus
from app.deps.events import get_event_bus

EventBusDep = Annotated[EventBus, Depends(get_event_bus)]

@router.post("")
async def create_order(service: OrderServiceDep, event_bus: EventBusDep, ...):
    uc = CreateOrderUseCase(service, event_bus)
    ...
```

---

## Creating a handler

### 1. Write the handler

```python
# app/core/events/handlers/orders.py
import logging
from app.core.events.dispatcher import dispatcher

logger = logging.getLogger(__name__)

@dispatcher.register("order.created")
async def send_order_confirmation(payload: dict) -> None:
    order_id = payload["order_id"]
    email = payload["email"]
    # ... send email (verify idempotency first!)
    logger.info("Sent confirmation for order %s to %s", order_id, email)
```

### 2. Register the module

```python
# app/core/events/handlers/__init__.py
import app.core.events.handlers.items   # noqa: F401
import app.core.events.handlers.orders  # noqa: F401  ← add this
```

### 3. Idempotency

Handlers that succeeded on a previous attempt are **automatically skipped** on retry thanks to per-handler state tracking (see [Handler state tracking](#handler-state-tracking) below). However, handlers should still be idempotent as a defence-in-depth measure — for example, if the process crashes after a handler succeeds but before the state is committed:

```python
@dispatcher.register("order.created")
async def send_order_confirmation(payload: dict) -> None:
    if await email_service.was_sent(ref=f"order-{payload['order_id']}"):
        return  # already sent
    await email_service.send(...)
```

---

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `OUTBOX_POLL_INTERVAL_SECONDS` | `30` | Fallback poll interval if NOTIFY is missed |
| `OUTBOX_MAX_RETRIES` | `5` | Default max retries before marking FAILED |
| `OUTBOX_HANDLER_TIMEOUT_SECONDS` | `30` | Per-handler execution timeout |
| `OUTBOX_CLEANUP_DAYS` | `30` | Retention period for PROCESSED events |
| `OUTBOX_CLEANUP_BATCH_SIZE` | `1000` | Batch size for cleanup DELETE operations |

All configurable via environment variables.

---

## Retry and backoff

When a handler fails:

1. `retry_count` is incremented.
2. `last_error` stores the full traceback of each failed handler.
3. `handler_state` records per-handler outcomes (see below).
4. `scheduled_at` is set to: `now() + min(2^retry_count + random(0-5s), 1 hour)`.
5. The event stays `PENDING` and will be picked up after `scheduled_at`.

The **jitter** (random 0-5s) prevents thundering herd when multiple events fail simultaneously (e.g., external service outage). The **cap** (1 hour) prevents absurd delays at high retry counts.

When `retry_count >= max_retries`, the event is marked `FAILED` with a **CRITICAL** log.

```
PENDING → retry (backoff) → retry (backoff) → ... → FAILED
                                                       │
                                              replay_failed_events()
                                                       │
                                                    PENDING (reset)
```

### Handler state tracking

The `handler_state` JSONB column on `outbox_events` records which handlers succeeded or failed on each attempt:

```json
{
  "log_item_created":     {"status": "ok",     "at": "2026-03-21T10:00:00+00:00"},
  "webhook_item_created": {"status": "failed", "at": "2026-03-21T10:00:01+00:00", "error": "TimeoutError..."}
}
```

On retry, the worker reads `handler_state` and passes the set of succeeded handler names to the dispatcher.  Handlers marked as `"ok"` are **skipped** — only failed or new handlers execute.  This prevents duplicate side effects (e.g., a webhook being sent multiple times for the same event).

The state is committed per event (not per batch) to minimise the crash window.

To force all handlers to re-execute during a replay (e.g., after deploying a handler fix):

```python
await replay_failed_events(reset_handler_state=True)
```

---

## Operations

### Cleanup

Delete old PROCESSED events (runs in batches to avoid lock contention):

```python
from app.core.events.cleanup import cleanup_processed_events

deleted = await cleanup_processed_events()          # uses OUTBOX_CLEANUP_DAYS
deleted = await cleanup_processed_events(days=7)    # override retention
```

### Replay failed events

Reset FAILED events back to PENDING for reprocessing:

```python
from app.core.events.cleanup import replay_failed_events

count = await replay_failed_events()                                    # all FAILED
count = await replay_failed_events(event_ids=[uuid1, uuid2])           # specific events
```

### Worker health

The worker is available on `app.state.outbox_worker`. It starts automatically in the lifespan if the database is healthy.

---

## Known limitations

### 1. Causal ordering not guaranteed

`FOR UPDATE SKIP LOCKED` with multiple workers does not guarantee that events for the same aggregate are processed in order. If `order.created` and `order.paid` arrive close together, a second worker may process `order.paid` first.

**Mitigation**: Handlers must be **state-aware** — verify the entity's current state in the database before acting:

```python
@dispatcher.register("order.paid")
async def process_payment(payload: dict) -> None:
    order = await order_repo.get(payload["order_id"])
    if order is None or order.status != "CREATED":
        raise EventPreconditionError("Order not ready for payment")
    # ... process payment
```

The exception triggers a retry with backoff, giving the prerequisite event time to be processed.

### 2. Timeout cancellation risk

`asyncio.wait_for` cancels handler coroutines on timeout. If a handler produced an external side effect (e.g., uploaded to S3) but didn't record it for idempotency, the retry may duplicate the effect.

**Mitigation**: Use `asyncio.shield()` for critical external operations:

```python
@dispatcher.register("order.invoice")
async def upload_invoice(payload: dict) -> None:
    result = await asyncio.shield(s3_client.upload(file))
    await mark_as_uploaded(payload["order_id"], result.key)
```

### 3. Handler state depends on `__name__`

The `handler_state` tracking uses each handler function's `__name__` as the key. If a handler is renamed during a deploy, the old `"ok"` entry won't match and the handler will re-execute on any pending retry.

**Mitigation**: This is generally harmless (the handler runs once more). For critical handlers, keep function names stable across deploys.

### 4. LISTEN connection is outside the pool

The worker maintains a dedicated asyncpg connection for `LISTEN`, separate from SQLAlchemy's connection pool. A heartbeat (`SELECT 1`) runs every poll cycle to detect dead connections. If the heartbeat fails, the worker reconnects with exponential backoff.
