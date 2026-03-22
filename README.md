# FastAPI Boilerplate

A solid foundation for building production-grade backends that scale from small projects to mid-large ones without accumulating infrastructure complexity. Includes a transactional event bus and a recurring job scheduler built entirely on PostgreSQL — no Redis, RabbitMQ, or Celery needed. A single database handles persistence, messaging, and scheduling, keeping the stack minimal while supporting multi-worker deployments out of the box.

- **Async everything** — SQLAlchemy 2.x + asyncpg, fully non-blocking from route to database
- **JWT auth** — Access + refresh tokens, Argon2 password hashing, permission-based guards
- **Transactional Outbox event bus** — Domain events persisted atomically and dispatched via PostgreSQL `LISTEN/NOTIFY` with per-handler retry, isolation, and timeout
- **Scheduled jobs** — Recurring tasks with `FOR UPDATE SKIP LOCKED` for multi-worker safety, no Redis or Celery required
- **Configurable connection pool** — `pool_size`, `max_overflow`, `pool_timeout` via env vars, safe defaults for multi-worker deployments
- **Structured logging + request tracing** — JSON logs in production, colored in development, per-request `request_id` across all layers. See `docs/logging.md`
- **Repository pattern** — Generic `BaseRepo[T]` with offset and cursor pagination, filtering, and field mapping
- **Use-case orchestration** — Thin use cases coordinate services and publish events, keeping business logic reusable
- **SQL-first migrations** — No Alembic; plain SQL schema, deltas, and seeds managed via shell scripts

## Stack

- Python 3.13+ / FastAPI / Pydantic v2
- SQLAlchemy 2.x async + asyncpg + PostgreSQL 16
- JWT (PyJWT) + Argon2 password hashing
- Docker + docker-compose

## Quick start

```bash
# 1. Start PostgreSQL
docker compose up db -d

# 2. Create schema and seed initial data
bash sql/reset.sh

# 3. Install dependencies
uv sync --extra dev

# 4. Install pre-commit hooks
uv run pre-commit install

# 5. Start the API
ENVIRONMENT=local uv run uvicorn main:app --reload

# 6. Open docs
open http://localhost:8000/docs
```

## Docker setup

```bash
docker compose up --build
bash sql/reset.sh  # in another terminal
```

## Project structure

```
app/
├── core/           # Config, DB, security, logging, exceptions, lifespan
│   ├── events/     # Event bus: dispatcher, worker, handlers, cleanup
│   └── jobs/       # Scheduled jobs: registry, worker, handlers
├── models/         # SQLAlchemy ORM (by domain: auth/, items/, events/)
├── schemas/        # Pydantic v2 request/response
├── repos/          # Async repositories with BaseRepo[T]
├── services/       # Business logic
├── use_cases/      # Orchestrators (coordinate services + publish events)
├── deps/           # FastAPI dependencies (auth, repos, event bus)
└── api/v1/         # HTTP routers
```

## Event bus

Persistent event bus using the **Transactional Outbox** pattern with PostgreSQL `LISTEN/NOTIFY`. Events are inserted atomically in the same DB transaction as business data and processed asynchronously by a background worker.

- Per-handler isolation with timeout and exponential backoff
- Succeeded handlers are skipped on retry (no duplicate side effects)
- Cleanup and replay utilities for production operations

See `docs/event-bus.md` for the full guide.

## Scheduled jobs

Recurring task scheduler using `FOR UPDATE SKIP LOCKED` for multi-worker safety. Each job is a single row in `scheduled_jobs` that self-reschedules after execution.

- Works with `uvicorn --workers N` — only one process runs each job per cycle
- Fixed interval scheduling with automatic rescheduling
- Stale recovery on startup (crashed `RUNNING` jobs reset to `PENDING`)

See `docs/jobs.md` for the full guide.

## Auth flow

```bash
# Register
curl -X POST http://localhost:8000/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"user@test.com","username":"user1","password":"pass123"}'

# Login
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user@test.com","password":"pass123"}'

# Use token
curl http://localhost:8000/v1/auth/me \
  -H "Authorization: Bearer <access_token>"

# Refresh
curl -X POST http://localhost:8000/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

## Tests

```bash
# Unit tests (no DB)
pytest tests/unit

# Integration tests (no real DB, mocks)
pytest tests/integration

# All
pytest
```

## SQL migrations

```bash
# Full reset (drop + schema + seeds)
bash sql/reset.sh

# Apply pending deltas
bash sql/apply.sh
```

See `docs/architecture.md` for the full guide on adding a new module.
