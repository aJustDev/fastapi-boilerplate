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
```

## Data flow

```
Request → Router → Dependency injection (auth + repo) → UseCase → Service → Repo → ORM → DB
                                                                                    ↓
Response ← Router ← Schema.model_validate(orm_obj) ←──────────────────────────────←─┘
```

## Key patterns

- **DI factory**: `get_repo(ItemRepo)` — one function for all repos
- **Exception hierarchy**: DomainException → UseCaseException/AuthException → specific errors. 4 global handlers.
- **Pagination**: offset (`list`) and cursor (`list_cursor`) in BaseRepo[T]
- **Filtering**: `map_field` dict on repos maps query params to columns + operators
- **Auth**: JWT access (30min) + refresh (7d) tokens. `CurrentUser` annotated dependency.

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
- English code, Spanish comments only if clarifying non-obvious logic
- Composition over inheritance
- No Alembic — SQL scripts only
