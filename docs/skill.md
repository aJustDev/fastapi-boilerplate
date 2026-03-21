---
name: development
description: Development workflow for the FastAPI boilerplate project. Use when writing code, adding features, creating modules, fixing bugs, or making any changes to the codebase. Covers layer responsibilities, coding conventions, SQL migration workflow, testing strategy, exception handling, and event bus usage.
---

# Development

## Before coding

1. Read the architecture reference for layer responsibilities and conventions
2. Check existing patterns in a similar module (e.g., `auth/` or `items/`)
3. Follow the "Adding a new module" checklist in the architecture reference

## Layer rules

- **Routers** (`api/v1/`) — Parse HTTP, call use cases, return schemas. No business logic.
- **Use cases** (`use_cases/`) — Orchestrate services. Thin (<20 lines). Publish events via `EventBus` when producing side effects.
- **Services** (`services/`) — Own business rules. Receive repos via constructor. Raise domain exceptions.
- **Repos** (`repos/`) — Extend `BaseRepo[T]`. Override `_base_select()` for eager loading. Configure `map_field` for filtering.
- **Models** (`models/`) — Use `IntPkMixin` + `AuditMixin`. Use `Mapped[]` annotations, not legacy `Column()`.
- **Event handlers** (`core/events/handlers/`) — Register via `@dispatcher.register("event.type")`. Must be idempotent.

## Exception handling

- Raise domain exceptions (`NotFoundError`, `ConflictError`, `AuthenticationError`, etc.)
- Never raise `HTTPException` from services/repos — global handlers convert domain exceptions to HTTP responses
- Custom exceptions: subclass `UseCaseException` (400-level) or `DomainException` (500-level)

## SQL changes

1. Update `sql/schema.sql` with the new DDL (source of truth for fresh installs)
2. Create `sql/deltas/NNN_description.sql` with the ALTER/CREATE statements
3. **Always** apply via `bash sql/apply.sh` — never use `psql` or `docker exec` directly, as that bypasses `_schema_migrations` tracking

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

- **Architecture and layers**: See [references/architecture.md](references/architecture.md) for full layer spec, data flow, key patterns, adding a new module checklist, and SQL management
- **Event bus**: See [references/event-bus.md](references/event-bus.md) for the Transactional Outbox pattern, publishing events, creating handlers, retry/backoff, cleanup, and known limitations
