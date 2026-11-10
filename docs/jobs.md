# Scheduled jobs

Recurring background tasks run at a fixed interval, stored as rows in `scheduled_jobs` and
executed by a `JobWorker` in every API process. PostgreSQL decides which worker runs each due
job, so a job runs once per interval whatever the number of processes or replicas. Use it for
periodic maintenance and polling: cleanups, digests, syncs.

## How it works

![Execution cycle of a job](img/jobs-cycle.svg)

Every `JOB_POLL_INTERVAL_SECONDS`, each worker (`app/core/jobs/worker.py`):

1. **Recovers** `RUNNING` jobs whose `lease_until` has passed (their worker died) back to
   `PENDING`, then reads the ids of up to 10 `PENDING` jobs with `next_run_at <= now()`.
2. **Claims** each one with `UPDATE ... SET status = 'RUNNING', claimed_by = 'host:pid',
   lease_until = now + JOB_LEASE_SECONDS WHERE id = :id AND status = 'PENDING' RETURNING ...`.
   No row back means another worker claimed it: skip.
3. **Runs** the handler with `JOB_HANDLER_TIMEOUT_SECONDS` and no transaction open.
4. **Reschedules** in one `UPDATE`: `PENDING`, `next_run_at = now + interval_seconds`,
   `last_run_at`, `last_error` (last 500 characters, or `NULL`), `run_count + 1`, lease cleared.
   A failing handler is rescheduled the same way.

## Usage

Register the handler in the context that owns it and import the module in
`app/db_registry.py` (infrastructure jobs live in `app/core/jobs/handlers/`):

```python
# app/<context>/jobs/cleanup.py
@job_registry.register("daily_cleanup")
async def daily_cleanup() -> None:
    async with async_session_factory() as session:
        ...
        await session.commit()
```

A handler takes no arguments and opens its own session. Then add the job row with a migration
(see `migrations/versions/0002_seed_reference_data.py`):

```python
def upgrade() -> None:
    op.execute(
        "INSERT INTO scheduled_jobs (job_name, description, interval_seconds) "
        "VALUES ('daily_cleanup', 'Removes stale temp data', 86400) "
        "ON CONFLICT (job_name) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM scheduled_jobs WHERE job_name = 'daily_cleanup'")
```

A row without a registered handler is claimed and rescheduled with
`last_error = "No handler registered for job ..."`.

Jobs of this boilerplate: `heartbeat_check` (every 5 min, logs the worker identity) and
`revoked_tokens_cleanup` (hourly, see `docs/auth.md`).

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `JOB_POLL_INTERVAL_SECONDS` | `15` | How often each worker looks for due jobs |
| `JOB_HANDLER_TIMEOUT_SECONDS` | `60` | Maximum run time of a handler |
| `JOB_LEASE_SECONDS` | `120` | How long a claimed job belongs to its worker; at least twice the handler timeout (validated at startup) |

## Operations

```sql
-- pause / resume
UPDATE scheduled_jobs SET status = 'DISABLED' WHERE job_name = 'daily_cleanup';
UPDATE scheduled_jobs SET status = 'PENDING', next_run_at = now() WHERE job_name = 'daily_cleanup';

-- run on the next poll
UPDATE scheduled_jobs SET next_run_at = now() WHERE job_name = 'daily_cleanup';

-- health
SELECT job_name, status, claimed_by, lease_until, run_count, last_run_at, next_run_at, last_error
FROM scheduled_jobs;
```

## Guarantees and limits

- A due job is claimed by exactly one worker.
- A job whose worker dies is recovered once its lease expires, by any worker, on its next poll.
- A job runs within one poll interval of `next_run_at`, not at an exact time.
- Fixed intervals only (no cron expressions); one timeout for every job; a failed job waits for
  its next interval.
- A handler that runs longer than `JOB_LEASE_SECONDS` can be recovered and run again while it is
  still running; the validator keeps the lease at twice the timeout to prevent it.
- For work per entity, a job can publish events and let the event bus handle each one with its
  retries (`docs/event-bus.md`).

## Files

| File | Role |
|---|---|
| `app/core/jobs/registry.py` | `job_registry` |
| `app/core/jobs/worker.py` | `JobWorker`: recovery, claim, run, reschedule |
| `app/core/jobs/models.py` | `ScheduledJobORM` |
| `app/core/jobs/handlers/heartbeat.py` | Example infrastructure job |
