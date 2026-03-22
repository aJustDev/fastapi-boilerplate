# Architecture Spec

## Layers (top → bottom)

```
api/v1/        → HTTP routers. Receives requests, delegates to use cases, returns schemas.
use_cases/     → Orchestrators. Thin classes that coordinate one or more services. No business logic.
services/      → Business logic. Each service owns the rules for its domain. Reusable across use cases.
repos/         → Data access. BaseRepo[T] async with offset + cursor pagination. One repo per model.
models/        → SQLAlchemy 2.x ORM. Mixins: IntPkMixin (BIGINT IDENTITY PK), AuditMixin (timestamps).
schemas/       → Pydantic v2. Request/response validation. from_attributes=True.
deps/          → FastAPI dependencies. get_session, get_repo(RepoClass), get_current_user, require_permissions.
core/          → Config, DB engine, security (JWT+Argon2), logging, exceptions, lifespan, middleware.
core/events/   → Transactional Outbox event bus: dispatcher, worker, handlers, cleanup.
core/jobs/     → Scheduled jobs: registry, worker, handlers. FOR UPDATE SKIP LOCKED.
```

## Data flow

```
Request → RequestIdMiddleware → Router → DI (auth + repo + event_bus) → UseCase → Service → Repo → ORM → DB
                                                     │                              ↓
                                                     └→ EventBus.publish() ──→ outbox_events
                                                                                    ↓
                                                                              Worker (async)
                                                                                    ↓
Response ← Router ← Schema.model_validate(orm_obj) ←──────────────────────←── Handlers
```

## Key patterns

- **DI factory**: `get_repo(ItemRepo)` — one function for all repos
- **Exception hierarchy**: DomainException → UseCaseException/AuthException → specific errors. 4 global handlers.
- **Pagination**: offset (`list`) and cursor (`list_cursor`) in BaseRepo[T]
- **Filtering**: `map_field` dict on repos maps query params to columns + operators
- **Auth**: JWT access (30min) + refresh (7d) tokens. `CurrentUser` annotated dependency.
- **Event bus**: Transactional Outbox with PostgreSQL `LISTEN/NOTIFY`. Use cases publish events via `EventBus`; a background worker dispatches them to handlers with isolation, timeout, and per-handler retry tracking. See `docs/event-bus.md`.
- **Scheduled jobs**: Recurring tasks using `FOR UPDATE SKIP LOCKED` for multi-worker safety. Self-rescheduling with fixed intervals. See `docs/jobs.md`.
- **Request tracing**: `RequestIdMiddleware` generates a unique `request_id` per request (via `ContextVar`), injected into every log line. Accepts `X-Request-ID` from client for end-to-end correlation. See `docs/logging.md`.
- **Connection pool**: `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT` configurable via env vars. Max connections per worker = `pool_size + max_overflow`. Total = that × number of workers.

## Adding a new module

1. `app/models/{domain}/` — ORM model(s) inheriting Base + mixins
2. `app/schemas/{domain}/` — Pydantic schemas (Create, Read, Update)
3. `app/repos/{domain}/` — Repo inheriting BaseRepo[T], configure map_field
4. `app/services/{domain}.py` — Service with business logic
5. `app/use_cases/{domain}/` — Use case(s) orchestrating the service
6. `app/api/v1/{domain}.py` — Router with endpoints
7. Register router in `app/api/v1/__init__.py`
8. Add SQL to `sql/schema.sql` + delta in `sql/deltas/`
9. Add tests in `tests/unit/{domain}/` and `tests/integration/{domain}/`
10. If the module publishes events: inject `EventBus` in use cases, add handlers in `app/core/events/handlers/`, register in `handlers/__init__.py`. See `docs/event-bus.md`.

## SQL management

- `sql/schema.sql` — full DDL (source of truth)
- `sql/deltas/NNN_description.sql` — incremental changes
- `sql/seeds/` — initial data
- `bash sql/reset.sh` — drop + recreate + schema + seeds
- `bash sql/apply.sh` — apply pending deltas (tracked in `_schema_migrations`)

## Conventions

- Python 3.13+, strict typing, Pydantic v2
- SQLAlchemy async with asyncpg
- Absolute imports from `app.`
- English
- Composition over inheritance
- No Alembic — SQL scripts only
