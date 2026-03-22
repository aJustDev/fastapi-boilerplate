# Scheduled Jobs

## What is it?

A recurring job scheduler built on the same `FOR UPDATE SKIP LOCKED` pattern as the event bus. Jobs are time-based tasks (like cron) that run at a fixed interval. Multiple worker processes can compete for the same job, but PostgreSQL row-level locking guarantees **exactly one** executes it per cycle.

- **No external dependencies**: Pure PostgreSQL — no Redis, Celery, or cron daemon.
- **Multi-worker safe**: Works with `uvicorn --workers N` out of the box.
- **Self-rescheduling**: After execution, the job automatically advances its `next_run_at`.

---

## Architecture

```
uvicorn --workers 3
  │
  ├── Worker PID=8  ─┐
  ├── Worker PID=9  ─┤──→ JobWorker (poll loop)
  └── Worker PID=10 ─┘         │
                                │  SELECT ... WHERE status='PENDING'
                                │  AND next_run_at <= now()
                                │  FOR UPDATE SKIP LOCKED
                                │
                          ┌─────▼──────┐
                          │ JobRegistry │  job_name → handler
                          └─────┬──────┘
                                │
                          ┌─────▼──────┐
                          │  Handler    │  (isolated, with timeout)
                          └────────────┘
```

Each worker process runs its own `JobWorker` instance. On each poll cycle, all workers query for due jobs simultaneously. PostgreSQL's `SKIP LOCKED` ensures only one claims each job — the others find zero rows and go idle.

---

## Quick start — Creating a job

### 1. Write the handler

```python
# app/core/jobs/handlers/cleanup.py
import logging

from app.core.jobs.registry import job_registry

logger = logging.getLogger(__name__)


@job_registry.register("daily_cleanup")
async def daily_cleanup() -> None:
    # ... your logic here
    logger.info("Cleanup done")
```

### 2. Register the module

```python
# app/core/jobs/handlers/__init__.py
import app.core.jobs.handlers.heartbeat  # noqa: F401
import app.core.jobs.handlers.cleanup    # noqa: F401  ← add this
```

### 3. Insert the job row

Jobs are defined as rows in `scheduled_jobs`. Add to seeds or insert manually:

```sql
INSERT INTO scheduled_jobs (job_name, description, interval_seconds, next_run_at)
VALUES ('daily_cleanup', 'Removes stale temp data', 86400, now())
ON CONFLICT (job_name) DO NOTHING;
```

For existing databases, use a delta migration:

```sql
-- sql/deltas/004_daily_cleanup_job.sql
INSERT INTO scheduled_jobs (job_name, description, interval_seconds, next_run_at)
VALUES ('daily_cleanup', 'Removes stale temp data', 86400, now())
ON CONFLICT (job_name) DO NOTHING;
```

---

## How it works

### Execution cycle

1. **Poll**: Every `JOB_POLL_INTERVAL_SECONDS` (default 15s), the worker queries for due jobs.
2. **Claim**: The worker sets `status='RUNNING'` and `claimed_by=hostname:PID`, then commits.
3. **Execute**: The handler runs with a timeout of `JOB_HANDLER_TIMEOUT_SECONDS`.
4. **Reschedule**: `next_run_at` advances by `interval_seconds`, `status` returns to `PENDING`, `run_count` increments.

```
PENDING → RUNNING → (execute) → PENDING (next_run_at += interval)
```

### Error handling

If a handler raises an exception:
- `last_error` stores the traceback (truncated to 500 chars).
- The job is **still rescheduled** — jobs always run on schedule, even after failure.
- Errors are logged at `EXCEPTION` level.

### Stale recovery

If a worker crashes while a job is `RUNNING`, the next worker startup resets all `RUNNING` jobs back to `PENDING`:

```python
UPDATE scheduled_jobs SET status = 'PENDING' WHERE status = 'RUNNING';
```

---

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `JOB_POLL_INTERVAL_SECONDS` | `15` | How often workers check for due jobs |
| `JOB_HANDLER_TIMEOUT_SECONDS` | `60` | Max execution time per handler |

All configurable via environment variables.

---

## Table schema

```sql
CREATE TABLE scheduled_jobs (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_name         VARCHAR(255) NOT NULL UNIQUE,
    description      TEXT,
    interval_seconds INT          NOT NULL,
    status           VARCHAR(20)  NOT NULL DEFAULT 'PENDING'
                         CHECK (status IN ('PENDING', 'RUNNING', 'DISABLED')),
    last_run_at      TIMESTAMPTZ,
    next_run_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    last_error       TEXT,
    run_count        INT          NOT NULL DEFAULT 0,
    claimed_by       TEXT,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ
);
```

Key columns:
- **`job_name`**: Unique identifier, maps to a handler in `JobRegistry`.
- **`interval_seconds`**: Time between executions (300 = every 5 minutes).
- **`status`**: `PENDING` (ready), `RUNNING` (claimed), `DISABLED` (paused).
- **`claimed_by`**: `hostname:PID` of the worker that last executed it.
- **`run_count`**: Total successful + failed executions.

---

## Operations

### Disable a job

```sql
UPDATE scheduled_jobs SET status = 'DISABLED' WHERE job_name = 'daily_cleanup';
```

The worker skips `DISABLED` jobs. To re-enable:

```sql
UPDATE scheduled_jobs SET status = 'PENDING', next_run_at = now() WHERE job_name = 'daily_cleanup';
```

### Check job health

```sql
SELECT job_name, status, claimed_by, run_count, last_run_at, next_run_at, last_error
FROM scheduled_jobs;
```

### Run a job immediately

```sql
UPDATE scheduled_jobs SET next_run_at = now() WHERE job_name = 'daily_cleanup';
```

---

## Differences from the event bus

| | Event Bus | Scheduled Jobs |
|---|-----------|----------------|
| Trigger | Domain event (use case publishes) | Time-based (interval) |
| Table | `outbox_events` (one row per event) | `scheduled_jobs` (one row per job, reused) |
| Handlers | Multiple per event type | One per job |
| Payload | Event-specific dict | None (handler reads from DB/config) |
| Retry | Exponential backoff, max retries → FAILED | Always reschedules on interval |
| Notification | LISTEN/NOTIFY | Poll only |

---

## Known limitations

### 1. Fixed interval only

The current implementation supports a fixed `interval_seconds`, not cron expressions. For most recurring tasks this is sufficient. Cron support can be added later with a library like `croniter`.

### 2. No per-job retry configuration

All jobs share the same timeout (`JOB_HANDLER_TIMEOUT_SECONDS`). A failed job doesn't retry sooner — it waits for the next scheduled interval.

### 3. Stale recovery resets all RUNNING jobs

On startup, all `RUNNING` jobs are reset to `PENDING`. If two workers start simultaneously, both may reset the same job. This is harmless (idempotent UPDATE) but worth noting.
