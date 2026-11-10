# Event bus

Transactional outbox on PostgreSQL. A use case publishes an event into the `outbox_events` table
in the same transaction as its business change; a worker in every API process dispatches it to
the handlers registered for its type, after the commit. Use it for side effects that must happen
if and only if the change is committed: emails, webhooks, work in another context.

## How it works

![Dispatch of one event](img/event-bus-dispatch.svg)

1. `EventBus.publish` inserts the event and calls `pg_notify('outbox_event_channel', <id>)`.
   PostgreSQL delivers the notification only when the transaction commits; on rollback the event
   and the notification disappear together.
2. `OutboxWorker` (`app/core/events/worker.py`) keeps a dedicated asyncpg connection with
   `LISTEN`. A notification wakes it; without one it polls every `OUTBOX_POLL_INTERVAL_SECONDS`.
3. Each wake-up processes up to 50 events, **one per transaction**: it locks the oldest due
   `PENDING` event with `FOR UPDATE SKIP LOCKED`, dispatches it and commits. Other workers skip
   the locked row and take the next one.
4. The dispatcher runs the event type's handlers in registration order, each with
   `OUTBOX_HANDLER_TIMEOUT_SECONDS`. A failing handler does not stop the others.
5. All handlers succeeded: the event is `PROCESSED`. Otherwise it stays `PENDING` with
   `scheduled_at = now + min(2^retry_count + random(0..5) s, 1 h)`, until `max_retries`, when it
   becomes `FAILED` (logged at CRITICAL). An event type without handlers counts as a failure.

`handler_state` (JSONB) records the outcome per handler; on a retry, handlers that already
succeeded are skipped.

## Usage

Publish from a use case, with the session of the request (`EventBus` is injected in the router
with `Depends(get_event_bus)`):

```python
@dataclass(slots=True)
class CreateItemUseCase:
    item_repo: ItemRepo
    event_bus: EventBus

    async def execute(self, ...) -> ItemORM:
        item = await self.item_repo.create(ItemORM(...))
        await self.event_bus.publish(event_type="item.created", payload={"item_id": item.id})
        return item
```

`publish(event_type, payload, *, aggregate_id=None, correlation_id=None)`: the payload must be
JSON-serializable; `aggregate_id` and `correlation_id` (UUIDs) are indexed for tracing.

Handle it in the context that reacts, and import the module in `app/db_registry.py`:

```python
# app/<context>/event_handlers/<name>.py
@dispatcher.register("item.created")
async def notify_owner(payload: dict) -> None:
    ...
```

A handler receives the payload only. It must be idempotent (see the limits) and should read the
current state of the entity from the database instead of trusting the payload.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `OUTBOX_POLL_INTERVAL_SECONDS` | `30` | Poll when no notification arrives |
| `OUTBOX_MAX_RETRIES` | `5` | Attempts before an event becomes `FAILED` |
| `OUTBOX_HANDLER_TIMEOUT_SECONDS` | `30` | Timeout of each handler |
| `OUTBOX_CLEANUP_DAYS` | `30` | Retention used by `cleanup_processed_events` |
| `OUTBOX_CLEANUP_BATCH_SIZE` | `1000` | Rows per `DELETE` batch of the cleanup |

## Operations

```python
from app.core.events.cleanup import cleanup_processed_events, replay_failed_events

await cleanup_processed_events(days=7)  # delete PROCESSED events older than 7 days
await replay_failed_events()            # FAILED -> PENDING, retry count reset
await replay_failed_events(event_ids=[...], reset_handler_state=True)  # re-run every handler
```

Neither runs on a schedule: call them from a job (`docs/jobs.md`) or a script.

## Guarantees and limits

- An event exists only if the business change committed, and it is dispatched after the commit.
- A pending event is handled by one worker at a time, with any number of processes or replicas.
- At least once, not exactly once: a crash after a handler's side effect and before the commit
  runs it again. Handlers must be idempotent.
- No ordering between events: with several workers, `item.updated` can run before
  `item.created`. A handler that depends on another event raises, and the retry gives it time.
- A handler that outlives its timeout is cancelled; protect external calls that must not be
  repeated with `asyncio.shield()` and record their result.
- `handler_state` is keyed by function name: renaming a handler re-runs it on pending retries.
- Each process keeps one extra connection for `LISTEN`, checked with `SELECT 1` on every cycle
  and reopened with backoff (up to 60 s) when it fails.

## Files

| File | Role |
|---|---|
| `app/core/events/bus.py` | `EventBus.publish` |
| `app/core/events/dispatcher.py` | Handler registry and dispatch |
| `app/core/events/worker.py` | `OutboxWorker`: LISTEN, poll, batch, retries |
| `app/core/events/cleanup.py` | Cleanup and replay |
| `app/core/events/models.py` | `OutboxEventORM` |
| `app/deps/events.py` | `get_event_bus` dependency |
