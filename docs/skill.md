---
name: development
description: Development workflow for the FastAPI boilerplate project. Use when writing code, adding features, creating modules, fixing bugs, or making any changes to the codebase. Covers layer responsibilities, coding conventions, Alembic migration workflow, testing strategy, exception handling, and event bus usage.
---

# Development

## Before coding

1. Read the architecture reference for layer responsibilities and conventions
2. Check existing patterns in a similar context (`app/auth/` or `app/items/`)
3. Follow the "Adding a new module" checklist in the architecture reference

## Layer rules

- **Routers** (`app/<context>/api/`) — Parse HTTP, call one use case, return schemas. No business logic.
- **Use cases** (`use_cases/`) — Orchestrate services (order of steps, own transactions, events). One per endpoint.
- **Services** (`services/`) — Own business rules. Receive repos via constructor. Raise domain exceptions.
- **Repos** (`repos/`) — Extend `BaseRepo[T]`. Override `_base_select()` for eager loading. Configure `map_field` for filtering.
- **Models** (`models/`) — Use `IntPkMixin` + `AuditMixin`. Use `Mapped[]` annotations, not legacy `Column()`.
- **Event handlers** (`app/<context>/event_handlers/`) — Register via `@dispatcher.register("event.type")`, import the module in `app/db_registry.py`. Must be idempotent.
- **Imports** — `uv run lint-imports` enforces the layer and context contracts in `.importlinter`.

## Exception handling

- Raise domain exceptions (`NotFoundError`, `ConflictError`, `AuthenticationError`, etc.)
- Never raise `HTTPException` from services/repos — global handlers convert domain exceptions to HTTP responses
- Custom exceptions: subclass `UseCaseException` (400-level) or `DomainException` (500-level)

## Schema changes

1. Change the models, then draft the migration: `uv run alembic revision --autogenerate --rev-id NNNN -m "..."`
2. Review the draft (renames, data, CONCURRENTLY and NOT VALID are not detected) and write a real `downgrade()`
3. Never edit an applied migration; never change the schema with `psql` directly. See `docs/migrations.md`

## Testing

- Unit tests: mock repos with `AsyncMock`, test services and use cases in isolation
- Integration tests: use `httpx.AsyncClient` + `ASGITransport`, override `get_session`
- Naming: `test_{feature}_{scenario}`
- Run: `uv run pytest`

## Before committing

1. Run tests: `uv run pytest`
2. Run linter: `uv run ruff check app/ tests/`
3. Run formatter: `uv run ruff format app/ tests/`

## Dependencies

- Add to `pyproject.toml` under `[project.dependencies]`
- Pin major versions: `"httpx>=0.28"`
- Run `uv sync` to install

## References

- **Architecture and layers**: See [references/architecture.md](references/architecture.md) for full layer spec, data flow, key patterns, adding a new module checklist, and schema management
- **Event bus**: See [references/event-bus.md](references/event-bus.md) for the Transactional Outbox pattern, publishing events, creating handlers, retry/backoff, cleanup, and known limitations
