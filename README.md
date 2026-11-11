# FastAPI Boilerplate

A solid foundation for building production-grade backends that scale from small projects to mid-large ones without accumulating infrastructure complexity. Includes a transactional event bus and a recurring job scheduler built entirely on PostgreSQL — no Redis, RabbitMQ, or Celery needed. A single database handles persistence, messaging, and scheduling, and both the event bus and the scheduler are safe with any number of processes or replicas.

- **Async everything** — SQLAlchemy 2.x + asyncpg, fully non-blocking from route to database
- **JWT auth** — Access tokens and single-use refresh tokens with reuse detection, Argon2 password hashing
- **Authorization** — A permission on every route and an ownership check on every resource, with a test that sends a second user against each route
- **Transactional Outbox event bus** — Domain events persisted atomically and dispatched via PostgreSQL `LISTEN/NOTIFY` with per-handler retry, isolation, and timeout
- **Scheduled jobs** — Recurring tasks claimed with an atomic conditional update and a lease, safe with several workers, no Redis or Celery required
- **Configurable connection pool** — `pool_size`, `max_overflow`, `pool_timeout` via env vars, safe defaults for multi-worker deployments
- **Structured logging + request tracing** — JSON logs in production, colored in development, per-request `request_id` across all layers. See `docs/logging.md`
- **Rate limiting** — Every endpoint is limited at its tier (`strict` for login/register/refresh, `default` for the rest), checked by a test. Counters are in memory, per process
- **Error contract** — Every error is `{detail, code}` with a stable code, and every route declares in OpenAPI the errors it answers; see `docs/errors.md`
- **HTTP hardening** — Security headers, trusted hosts and proxies, database timeouts; see `docs/security.md`
- **Prometheus metrics** — Request count, latency histograms, DB pool health and outbox counters at `/v1/metrics`, per process. See `docs/metrics.md`
- **Operations** — Health probes that follow the database, `python -m app.cli` (first admin, outbox replay, a worker-only process) and a deployment guide. See `docs/operations.md` and `docs/deployment.md`
- **Repository pattern** — Generic `BaseRepo[T]` with offset and cursor pagination, filtering, and field mapping
- **Bounded contexts** — `app/<context>/` with its own layers; use cases orchestrate services; import-linter enforces the boundaries
- **Alembic migrations** — Async `env.py`, reference data as migrations, applied by a separate `migrate` step; tests fail if the models and the migrated schema drift apart
- **Tests at four levels** — Unit, functional, integration on real PostgreSQL, and whole requests against it; meta-tests keep the rules above true
- **An example worth reading** — Workshops with limited seats and a waiting list: a state machine, a multi-row transaction under a row lock tested with simultaneous requests, idempotent enrollment, events and jobs. See `docs/workshops.md`, and how to remove it in `docs/architecture.md`

## Stack

- Python 3.14 / FastAPI / Pydantic v2
- SQLAlchemy 2.1 async + asyncpg + PostgreSQL 18, Alembic
- JWT (PyJWT) + Argon2 password hashing
- Docker + docker-compose

## Quick start

```bash
# 1. Local settings: the app and docker compose both read .env.local
cp .env.example .env.local

# 2. Start PostgreSQL
docker compose up db -d

# 3. Install dependencies (dev group included)
uv sync

# 4. Apply migrations and add development data (admin@example.com / admin123)
uv run alembic upgrade head
uv run python scripts/seed_dev.py

# 5. Install git hooks (pre-commit + pre-push)
bash scripts/install-hooks.sh

# 6. Start the API
uv run uvicorn main:app --reload

# 7. Interactive docs: http://localhost:8000/docs
```

## Docker setup

```bash
cp .env.example .env.local  # once
docker compose up --build   # db, then migrate (alembic upgrade head), then api
docker compose exec api python scripts/seed_dev.py
```

## Project structure

```
app/
  core/          Infrastructure: config, db, security, logging, metrics, exceptions,
                 event bus (events/), scheduled jobs (jobs/), middleware, lifespan
  deps/          FastAPI dependencies shared by every context (session, repos, current user)
  api/v1/        Composes the context routers, plus health and metrics
  auth/          Context: users, roles, permissions, tokens
  workshops/     Context: the example (seats, waiting list, events, jobs)
  db_registry.py Imports every model and handler module
  cli.py         python -m app.cli: first admin, outbox maintenance, worker process
migrations/      Alembic revisions
tests/           unit/, functional/, integration/, each split by context
```

Each context has its own `models/ schemas/ repos/ services/ use_cases/ api/` layers. Use cases
orchestrate services, services hold the business rules, and import-linter keeps contexts and
layers apart. See `docs/architecture.md`.

## Event bus

Persistent event bus using the **Transactional Outbox** pattern with PostgreSQL `LISTEN/NOTIFY`. Events are inserted atomically in the same DB transaction as business data and processed asynchronously by a background worker.

- One event per transaction: safe with several workers or replicas
- Woken up by NOTIFY on commit, with polling as fallback
- Per-handler isolation with timeout and exponential backoff
- Succeeded handlers are skipped on retry; delivery is at least once, so handlers are idempotent
- A daily cleanup job, and a command to replay failed events

See `docs/event-bus.md` for the full guide.

## Scheduled jobs

Recurring task scheduler where each job is a single row in `scheduled_jobs` that self-reschedules after execution. Jobs are claimed with an atomic conditional update, so only one worker runs each due job.

- Works with `uvicorn --workers N` — only one process runs each job per cycle
- Fixed interval scheduling with automatic rescheduling
- Lease per claimed job: jobs of a crashed worker are recovered once the lease expires

See `docs/jobs.md` for the full guide.

## Auth flow

```bash
# Register (password: at least 8 characters)
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","username":"user1","password":"pass1234"}'

# Login (OAuth2 form, not JSON)
curl -X POST http://localhost:8000/v1/auth/login \
  -d "username=user@test.com&password=pass1234"

# Use token
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer <access_token>"

# Refresh (the old refresh token stops working)
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'

# Logout (revokes both tokens)
curl -X POST http://localhost:8000/v1/auth/logout \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

See `docs/auth.md` for rotation, reuse detection and the rest of the session model.

## Tests

```bash
uv run pytest tests/unit          # unit: no DB, no HTTP
uv run pytest tests/functional    # functional: HTTP through the app, DB mocked
uv run pytest tests/integration   # integration: real PostgreSQL via testcontainers (Docker),
                                  # including whole requests in tests/integration/api
uv run pytest                     # all of them

bash scripts/ci-local.sh          # everything CI checks, in the same order
```

See `docs/testing.md` and `docs/tooling.md`.

## Migrations

```bash
uv run alembic upgrade head                                  # apply pending migrations
uv run alembic revision --autogenerate --rev-id 0010 -m "describe change"  # draft the next one
```

See `docs/migrations.md`.

See `docs/architecture.md` for the full guide on adding a new module.

## Docs

- `docs/architecture.md`: layers, how to add a context, how to start a project from this base and replace the example
- `docs/workshops.md`: the example context
- `docs/database.md`, `docs/migrations.md`: sessions, models, repositories and schema changes
- `docs/configuration.md`: settings, env files and validators
- `docs/auth.md`, `docs/event-bus.md`, `docs/jobs.md`, `docs/logging.md`, `docs/metrics.md`
- `docs/errors.md`, `docs/security.md`
- `docs/operations.md`, `docs/deployment.md`: health endpoints, the command line, going to production
- `docs/releases.md`: versions and how a release is cut and published
- `docs/testing.md`, `docs/tooling.md`, `docs/docker.md`
- `docs/adr/`: architecture decision records
- `CHANGELOG.md`
