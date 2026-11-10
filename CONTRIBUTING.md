# Contributing

## Prerequisites

- Python 3.14 (`uv` installs it from `.python-version`)
- [uv](https://docs.astral.sh/uv/)
- Docker and docker-compose
- PostgreSQL 18 (or use the container)

## Environment setup

```bash
git clone <repo-url>
cd fastapi
cp .env.example .env.local
uv sync
bash scripts/install-hooks.sh

docker compose up db -d
uv run alembic upgrade head
uv run python scripts/seed_dev.py
uv run uvicorn main:app --reload
```

## Workflow

1. Create a branch from `main`: `git switch -c feat/my-change`
2. Implement following the layer rules (see `docs/architecture.md`)
3. Add unit and/or integration tests
4. Atomic commits grouped by responsibility (see commits section)
5. Open a PR against `main`

The pre-commit hook runs ruff (check + format) on staged files, and the pre-push hook blocks direct pushes to `main`. Before opening a PR, `bash scripts/ci-local.sh` runs the same checks as CI (see `docs/tooling.md`). Add a line to `CHANGELOG.md` under `[Unreleased]` when the change is visible to users of the boilerplate.

## Commit conventions

Format: `type(scope): short lowercase description`

Types:
- `feat` — new functionality
- `fix` — bug fix
- `refactor` — restructuring with no behavior change
- `test` — new or modified tests
- `docs` — documentation
- `chore` — configuration, dependencies, CI

Common scopes: a context (`auth`, `items`) or a piece of infrastructure (`core`, `db`, `events`, `jobs`, `metrics`, `logging`, `migrations`, `deps`, `docker`)

Each commit must be atomic: a single responsibility change that compiles and passes tests on its own.

## Layer rules

Code lives in a context (`app/auth`, `app/items`), and inside it in layers. The full table and
the rules are in `docs/architecture.md`; the short version:

- Routers parse HTTP and call **one** use case.
- Use cases orchestrate services; services hold the business rules; plain CRUD may go from use
  case to repository.
- Repositories flush, never commit; models and schemas carry no logic.
- Contexts do not import each other, and `app/core` imports no context. `uv run lint-imports`
  checks it.

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

Follow the checklist in `docs/architecture.md`, section "Adding a context". A feature in an
existing context only adds files to its layers (`app/<context>/models`, `schemas`, `repos`,
`services`, `use_cases`, `api`), a migration and tests in `tests/{unit,functional,integration}/<context>/`.

## Schema changes

1. Change the models
2. `uv run alembic revision --autogenerate --rev-id NNNN -m "describe change"` and review the draft
3. Run the integration tests: they fail if models and migrations differ or a downgrade is broken

See `docs/migrations.md` for the rules on tables with data.

## Dependencies

```bash
# Production
uv add package

# Development
uv add --dev package
```

Always commit `pyproject.toml` and `uv.lock` together.
