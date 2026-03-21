# Contributing

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Docker and docker-compose
- PostgreSQL 16 (or use the container)

## Environment setup

```bash
git clone <repo-url>
cd fastapi
uv sync --extra dev
uv run pre-commit install

docker compose up db -d
bash sql/reset.sh
ENVIRONMENT=local uv run uvicorn main:app --reload
```

## Workflow

1. Create a branch from `main`: `git switch -c feat/my-change`
2. Implement following the layer rules (see `docs/skill.md`)
3. Add unit and/or integration tests
4. Atomic commits grouped by responsibility (see commits section)
5. Open a PR against `main`

Pre-commit hooks automatically run ruff (check + format) and pytest before each commit.

## Commit conventions

Format: `type(scope): short lowercase description`

Types:
- `feat` — new functionality
- `fix` — bug fix
- `refactor` — restructuring with no behavior change
- `test` — new or modified tests
- `docs` — documentation
- `chore` — configuration, dependencies, CI

Common scopes: `core`, `models`, `schemas`, `repos`, `services`, `use-cases`, `deps`, `api`, `sql`, `docker`

Each commit must be atomic: a single responsibility change that compiles and passes tests on its own.

## Layer rules

| Layer | Responsibility | Forbidden |
|-------|---------------|-----------|
| `api/` | Parse HTTP, delegate to use cases, return schemas | Business logic, DB access |
| `use_cases/` | Orchestrate services | Business logic, more than 20 lines |
| `services/` | Business rules | FastAPI imports, HTTPException |
| `repos/` | Data access via BaseRepo[T] | Business logic |
| `models/` | ORM definitions | Logic, queries |
| `schemas/` | Request/response validation | Logic, DB access |

## Exceptions

- Use the domain hierarchy: `NotFoundError`, `ConflictError`, `AuthenticationError`, etc.
- **Never** raise `HTTPException` from services or repos
- Global handlers convert domain exceptions to HTTP responses

## Testing

```bash
# Unit (no DB, mocks)
uv run pytest tests/unit -v

# Integration (no real DB, session override)
uv run pytest tests/integration -v

# With coverage
uv run pytest --cov=app --cov-report=term-missing
```

Guidelines:
- Unit: mock repos with `AsyncMock`, test services and use cases in isolation
- Integration: `httpx.AsyncClient` + `ASGITransport`, override `get_session`
- Naming: `test_{feature}_{scenario}`

## Adding a new module

Follow the checklist in `docs/architecture.md` section "Adding a new module":

1. ORM model in `app/models/{domain}/`
2. Schemas in `app/schemas/{domain}/`
3. Repo in `app/repos/{domain}/`
4. Service in `app/services/{domain}.py`
5. Use cases in `app/use_cases/{domain}/`
6. Router in `app/api/v1/{domain}.py`
7. Register router in `app/api/v1/__init__.py`
8. DDL in `sql/schema.sql` + delta in `sql/deltas/`
9. Tests in `tests/unit/{domain}/` and `tests/integration/{domain}/`

## SQL changes

1. Update `sql/schema.sql` (source of truth)
2. Create delta in `sql/deltas/NNN_description.sql`
3. Test with `bash sql/reset.sh` (clean environment) and `bash sql/apply.sh` (incremental)

## Dependencies

```bash
# Production
uv add package

# Development
uv add --dev package
```

Always commit `pyproject.toml` and `uv.lock` together.
