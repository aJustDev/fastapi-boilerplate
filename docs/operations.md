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
against a rate limit, and neither leaves an access line. An outage is logged when it starts
(`Not ready: the database does not answer (...)`, WARNING) and when it ends (`Ready again`,
INFO), not on every probe.

Startup does not wait for the database. The API starts, the startup log shows the database as
`unavailable` and the workers as `waiting for the database`, and both workers keep retrying until
it answers.

## Startup log

Each server logs, once, what it started with. The processes of one uvicorn take an advisory lock
and only the one that gets it prints the table; the others log `Process ready (pid N)`. Without a
database there is no lock, and every process prints it. On a terminal:

```
Startup summary
  ┌────────────────────────────────────────────────────────────────────────────┐
  │ FastAPI App v0.1.0                   local | log DEBUG | pid 2817 on api-1 │
  ├──────┬──────────┬──────────────────────────────────────────────────────────┤
  │  ok  │ Database │ localhost:5434/app_db, pool 5 + 10 overflow, timeout 30s │
  │  ok  │ Capacity │ up to 16 from this instance, 12 of 100 in use            │
  │  ok  │ Outbox   │ listening for events                                     │
  │  ok  │ Jobs     │ 5 handlers                                               │
  │  on  │ Limits   │ 60/minute, strict 5/minute, in memory per process        │
  │ off  │ Docs     │                                                          │
  │  on  │ Metrics  │ /v1/metrics, no token                                    │
  └──────┴──────────┴──────────────────────────────────────────────────────────┘
```

The first column is what to look at; on a color terminal it is green when the piece works,
yellow when it needs a look, red when it does not work, and the rows of what is off are grey.

| State | Means |
|---|---|
| `ok` | Working: the database answers and its schema matches the code, a worker is running |
| `warn` | The database schema is not the head of the migrations shipped with the code (a warning follows, `Database schema is at 0002 but this code expects 0009: ...`); this instance alone can open more connections than the server takes; behind a pooler, `DB_DIRECT_URL` is not set |
| `down` | The database did not answer at startup |
| `wait` | The worker started and retries until the database answers |
| `on`, `off` | A feature turned on or off by its setting (`RATE_LIMIT_ENABLED`, `DOCS_ENABLED`, `METRICS_ENABLED`; `OUTBOX_WORKER_ENABLED`, `JOB_WORKER_ENABLED` for the workers, shown as `not in this process`) |

The database is shown as host, port and name, never with its credentials, followed by the size
of the pool. Its schema revision appears only when there is something to say: under `warn` the
revision against the one the code expects (`no schema` for a database never migrated), and
without `migrations/` in the image the revision alone, since there is nothing to compare it with.
`Capacity` is what this instance can open, every process with its pool, its overflow and the
`LISTEN` of the outbox, against `max_connections` minus the connections reserved for superusers,
and how many are in use. It is `warn` when the instance alone does not fit; it cannot see other
replicas, so the sum for a deployment is in `docs/deployment.md`. With `DB_TRANSACTION_POOLER`
the row is `Pooler` instead: the server's limit is the pooler's, and the row says whether
`LISTEN` and the migrations go straight to PostgreSQL (`DB_DIRECT_URL`) or the outbox works by
polling. Behind a pooler every process prints its table, because the session lock that picks one
would stay on a server connection lent to others.

`Jobs` counts the handlers registered in code, not their rows. With several processes the first
line ends with their number.

In JSON the message is the title line alone, `FastAPI App v0.1.0 | local | log DEBUG | ...`, and
the facts travel in a `startup` field (`host`, `pid`, `processes`, `db` with `instance_max`,
`capacity` and `pooler`, `pool`, `outbox`, `jobs`, `rate_limit`, `docs`, `metrics`), so a log query can find, for example, the instances that started
without a metrics token.

Uvicorn then logs `Application startup complete.` and the address it listens on (with `--reload`
or `--workers`, the parent process logs the address first).

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
| `app/core/lifespan.py` | Startup and shutdown: workers, startup log, `ready` flag |
| `app/core/startup.py` | Time zone and database checks, the startup log |
| `app/cli.py` | `python -m app.cli` |
