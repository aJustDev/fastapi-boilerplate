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
   Each attempt that fails is one WARNING line:
   `Retry 1/12 of enrollment.confirmed 2d42... in 5s: notifications.notify_confirmed failed
   (WebhookRejectedError: webhook answered 503)`. A failure the handler can name (an
   `ExpectedFailure`, or its timeout) is that one line on every attempt, and the line is what
   is stored. Any other exception is a bug: the first and the last attempt also bring its
   traceback (after the line on a terminal, as the `exception` field in JSON), so it can be
   debugged at once, and it is stored with the event (`last_error`, `handler_state`).

`handler_state` (JSONB) records the outcome per handler; on a retry, handlers that already
succeeded are skipped.

## Usage

Publish from a use case, with the session of the request (`EventBus` is injected in the router
with `Depends(get_event_bus)`):

```python
@dataclass(slots=True)
class SeatingService:
    enrollment_repo: EnrollmentRepo
    event_bus: EventBus

    async def enroll(self, workshop: LockedWorkshop, attendee_id: int) -> ...:
        enrollment = await self.enrollment_repo.create(EnrollmentORM(...))
        await self.event_bus.publish(
            "enrollment.confirmed", {"enrollment_id": enrollment.id}, aggregate_id=enrollment.id
        )
```

`publish(event_type, payload, *, aggregate_id=None, correlation_id=None)`: the payload must be
JSON-serializable. `aggregate_id` is the id of the entity the event is about. `correlation_id`
defaults to the id of the current request, and the worker restores it while it handles the event,
so the lines of the handlers and of the worker carry the `request_id` of the request that
published it. Both are text columns, indexed for tracing.

`publish_many(event_type, [(aggregate_id, payload), ...])` stores one event per pair in one
batch, with a single NOTIFY. It is for a change that concerns many recipients (cancelling a
workshop tells every attendee): each one gets its own event, retried on its own.

Handle it in the context that reacts, and import the module in `app/db_registry.py`:

```python
# app/<context>/event_handlers/<name>.py
@dispatcher.register("enrollment.confirmed")
async def notify_confirmed(payload: dict, event_id: uuid.UUID) -> None:
    response = await client.post(url, json=payload, headers={"Idempotency-Key": str(event_id)})
    if not response.is_success:
        raise WebhookRejectedError(response.status_code)  # an ExpectedFailure
```

A handler receives the payload and the id of the event, and has two duties:

- **Raise unless the work was done.** A handler that returns is marked as done for good; one that
  raises is retried with backoff. An HTTP answer is not a delivery: check the status. For a
  failure it can name (the receiver said no, did not answer), raise a subclass of
  `ExpectedFailure` (`app/core/events/dispatcher.py`) with a short message: it is logged in one
  line, without a traceback. Do not let an HTTP client's own error through: httpx puts the URL
  in its messages, and a webhook URL often carries a secret.
- **Be idempotent** (see the limits). The event id is the same on every attempt: pass it as the
  idempotency key of external calls, or record it. Read the current state of the entity from the
  database instead of trusting the payload.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `OUTBOX_POLL_INTERVAL_SECONDS` | `30` | Poll when no notification arrives |
| `OUTBOX_MAX_RETRIES` | `12` | Attempts before an event becomes `FAILED`. The wait doubles each time (2 s, 4 s, ...): 12 attempts span a little over an hour |
| `OUTBOX_WORKER_ENABLED` | `true` | Run the worker in the API process (`docs/operations.md`) |
| `OUTBOX_HANDLER_TIMEOUT_SECONDS` | `30` | Timeout of each handler |
| `OUTBOX_CLEANUP_DAYS` | `30` | Retention used by `cleanup_processed_events` |
| `OUTBOX_CLEANUP_BATCH_SIZE` | `1000` | Rows per `DELETE` batch of the cleanup |

## Operations

- **Cleanup** is a scheduled job: `outbox_cleanup` deletes `PROCESSED` events older than
  `OUTBOX_CLEANUP_DAYS` once a day (`app/core/jobs/handlers/outbox_cleanup.py`). `FAILED` events
  are kept until someone replays or removes them.
- **Replay** is a command: `python -m app.cli outbox replay` puts `FAILED` events back to
  `PENDING` (`docs/operations.md`). Replay after fixing what made the handlers fail.
- **Watch** `outbox_events_failed_total` (`docs/metrics.md`): any increase is an event that needs
  a decision. Each one is also logged at CRITICAL with its id and what failed.

## Guarantees and limits

- An event exists only if the business change committed, and it is dispatched after the commit.
- A pending event is handled by one worker at a time, with any number of processes or replicas.
- At least once, not exactly once: a crash after a handler's side effect and before the commit
  runs it again. Handlers must be idempotent.
- No ordering between events: with several workers, `enrollment.cancelled` can run before the
  `enrollment.confirmed` of the same enrollment. A handler that depends on another event raises,
  and the retry gives it time.
- A handler that outlives its timeout is cancelled; protect external calls that must not be
  repeated with `asyncio.shield()` and record their result.
- `handler_state` is keyed by the module and qualified name of each handler, so two contexts may
  name their handlers alike. Moving or renaming a handler re-runs it on pending retries, and
  registering the same handler twice for an event fails at import.
- Each process keeps one extra connection for `LISTEN`, checked with `SELECT 1` on every cycle
  and reopened with backoff (up to 60 s) when it fails. It goes to `DB_DIRECT_URL` when set: a
  pooler in transaction mode lends connections per transaction, so a `LISTEN` through it would
  never hear its notifications and the worker would only poll (`docs/deployment.md`).

## Files

| File | Role |
|---|---|
| `app/core/events/bus.py` | `EventBus.publish` |
| `app/core/events/dispatcher.py` | Handler registry and dispatch |
| `app/core/events/worker.py` | `OutboxWorker`: LISTEN, poll, batch, retries |
| `app/core/events/cleanup.py` | Cleanup and replay |
| `app/core/jobs/handlers/outbox_cleanup.py` | The daily cleanup job |
| `app/core/events/models.py` | `OutboxEventORM` |
| `app/deps/events.py` | `get_event_bus` dependency |
