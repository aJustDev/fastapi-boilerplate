# Operations

What an operator uses once the app is running: the health endpoints an orchestrator probes, the
command line for tasks that are not HTTP requests, and the options for running the background
workers.

## Health endpoints

| Endpoint | Answers | Use it as |
|---|---|---|
| `GET /v1/health/liveness` | 200 `{"status": "alive"}` while the process serves requests | Liveness probe, container `HEALTHCHECK` |
| `GET /v1/health/readiness` | 200 `{"status": "ready"}`, or 503 | Readiness probe |

Readiness asks the database on every call (`SELECT 1`, at most 2 seconds), so it follows the
database: an instance that loses it, or starts before it is up, answers 503
`{"status": "database unavailable"}` and comes back by itself. `{"status": "not ready"}` is only
the window in which the process starts or shuts down. Neither endpoint needs a token or counts
against a rate limit.

Startup does not wait for the database. The API starts, the banner shows `DB: UNAVAILABLE` and
the workers as `WAITING`, and both workers keep retrying until it answers.

## Command line

`python -m app.cli <command>` runs with the same settings as the API. It is inside the image:

```bash
docker run --rm --env-file .env.prod --entrypoint python app -m app.cli <command>
```

| Command | Does |
|---|---|
| `create-admin --email E [--username U]` | Creates an account with the `admin` role, or gives the role to the account with that email. The password of a new account comes from `ADMIN_PASSWORD` or a prompt, never from an argument |
| `outbox replay [--id UUID ...] [--reset-handlers]` | Puts `FAILED` events back to `PENDING` with their retries reset; `--reset-handlers` also re-runs the handlers that had succeeded |
| `outbox cleanup [--days N]` | Deletes `PROCESSED` events older than N days now (default `OUTBOX_CLEANUP_DAYS`) |
| `worker` | Runs the outbox and job workers without the API, until SIGINT or SIGTERM |

`create-admin` is how the first administrator of a deployment comes to exist: registration only
grants the `user` role and no endpoint assigns roles (`docs/auth.md`).

## Background workers

The outbox worker (`docs/event-bus.md`) and the job worker (`docs/jobs.md`) run inside every API
process by default. PostgreSQL arbitrates between them, so any number of processes is safe.

| Setting | Default | Meaning |
|---|---|---|
| `OUTBOX_WORKER_ENABLED` | `true` | Run the outbox worker in the API process |
| `JOB_WORKER_ENABLED` | `true` | Run the job worker in the API process |

To scale the API and the workers apart, set both to `false` for the API and run
`python -m app.cli worker` as its own process or container. Each process that runs the outbox
worker keeps one extra database connection for `LISTEN`.

## Guarantees and limits

- A worker that cannot reach the database retries on its own: the outbox listener reconnects with
  backoff up to 60 s, the job worker tries again on its next poll.
- When a job handler is registered without its row in `scheduled_jobs`, or a row has no handler,
  the job worker logs a warning once at startup; `tests/integration/core/test_job_rows.py` fails
  for the jobs of this code base.
- On SIGTERM a handler or a job that is running is cancelled: the event stays `PENDING` and is
  dispatched again, the job is recovered when its lease expires. Handlers must be idempotent.

## Files

| File | Role |
|---|---|
| `app/api/v1/health.py` | Liveness and readiness |
| `app/core/lifespan.py` | Startup and shutdown: workers, banner, `ready` flag |
| `app/cli.py` | `python -m app.cli` |
