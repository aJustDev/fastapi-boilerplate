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
3. Add tests at the level that can see the change (see `docs/testing.md`)
4. Atomic commits grouped by responsibility (see commits section)
5. Open a PR against `main`

The pre-commit hook runs ruff (check + format) on staged files, and the pre-push hook blocks direct pushes to `main`. Before opening a PR, `bash scripts/ci-local.sh` runs the same checks as CI (see `docs/tooling.md`). Add a line to `CHANGELOG.md` under `[Unreleased]` when the change is visible to users of the boilerplate.

## Commit conventions

Format: `type(scope): short lowercase description`

Types:
- `feat` — new functionality
- `fix` — bug fix
- `refactor` — restructuring with no behavior change
- `perf` — a change made for speed or resource use
- `test` — new or modified tests
- `docs` — documentation
- `build` — dependencies, the image
- `ci` — workflows
- `chore` — configuration and housekeeping

Common scopes: a context (`auth`, `workshops`) or a piece of infrastructure (`core`, `db`, `events`, `jobs`, `metrics`, `logging`, `migrations`, `deps`, `docker`)

Each commit must be atomic: a single responsibility change that compiles and passes tests on its own.

## Layer rules

Code lives in a context (`app/auth`, `app/workshops`), and inside it in layers. The full table and
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
uv run pytest tests/unit -v          # no I/O: collaborators mocked
uv run pytest tests/functional -v    # HTTP through the app, session mocked
uv run pytest tests/integration -v   # real PostgreSQL (Docker): SQL, workers, whole requests
uv run pytest --cov=app --cov-report=term-missing
```

Guidelines (`docs/testing.md` has the fixtures of each level):
- Unit: mock repos with `AsyncMock`, test services and use cases in isolation
- Functional: `client` (`httpx.AsyncClient` + `ASGITransport`), patch repository methods
- Integration: a real repository on `db_session`; a whole request with `api_client` in
  `tests/integration/api/`, the level for anything about what is stored or who may touch it
- A test for a bug fails against the code before the fix: check it once
- Naming: `test_{what_must_hold}`

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
