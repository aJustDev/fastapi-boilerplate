# FastAPI Boilerplate

Reusable FastAPI boilerplate with async SQLAlchemy, JWT auth, and layered architecture.

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
│   └── events/     # Event bus: dispatcher, worker, handlers, cleanup
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
