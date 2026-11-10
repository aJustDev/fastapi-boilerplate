# fastapi-boilerplate

Starting point for FastAPI backends: Python 3.14, FastAPI, SQLAlchemy 2.1 async + asyncpg,
PostgreSQL 18 (also the event bus and the job scheduler), Alembic. Path-scoped rules live in
`.claude/rules/` and load when the matching files are edited.

## Sources of truth

- Layout, layers and import rules: `docs/architecture.md`
- One doc per feature or structural piece: `docs/README.md` (index)
- Decisions: `docs/adr/` (stack, Alembic, bounded contexts)
- History: `CHANGELOG.md`

## Structure

```
app/core/         infrastructure (config, db, repo, schema, security, events, jobs, logging,
                  metrics, middleware, exceptions); imports no context
app/deps/         dependencies shared by every context
app/api/v1/       composes the context routers, plus health and metrics
app/<context>/    auth, workshops (the example): models/ schemas/ repos/ services/ use_cases/
                  api/ (+ event_handlers/, jobs/, exceptions.py)
app/db_registry.py  imports every model and handler module
app/cli.py        python -m app.cli: create-admin, outbox replay/cleanup, worker
migrations/       Alembic revisions
tests/            unit/ functional/ integration/ (with integration/api/: whole requests on
                  PostgreSQL), each split by context
```

Request flow: router -> one use case -> services (business rules) -> repos -> models.
Use cases orchestrate; plain CRUD may go from use case to repository. Every route has a
permission guard and a rate limit; anything addressed by id is checked for ownership in its use
case; the session commits before the response is sent.

## Commands

- `uv sync` - install (dev group included)
- `bash scripts/install-hooks.sh` - pre-commit (ruff) and pre-push (blocks pushes to `main`)
- `bash scripts/ci-local.sh` - everything CI runs (`SKIP_INTEGRATION=1` without Docker)
- `uv run pytest` - all tests; `--ignore=tests/integration` without Docker
- `uv run ruff check app tests migrations scripts main.py docs/img` / `uv run ruff format ...`
- `uv run mypy app main.py`, `uv run lint-imports`
- `uv run alembic upgrade head`, `uv run alembic revision --autogenerate --rev-id NNNN -m "..."`
- `uv run python scripts/seed_dev.py` - local admin (admin@example.com / admin123) and sample workshops
- `uv run python -m app.cli --help` - create-admin, outbox replay/cleanup, worker
- `docker compose up --build` - db, migrate, api (needs `.env.local`: `cp .env.example .env.local`)

## Conventions

- **English** in code, commits, PRs, branches, docs, ADRs and CHANGELOG.
- Commits: `<type>(<scope>): <description>`, types `feat fix refactor test docs chore build ci perf`.
  Branches `feat/`, `fix/`, `refactor/`, `chore/`, `docs/`. Every change goes through a PR to `main`.
- A change visible to users of the boilerplate adds one line under `[Unreleased]` in `CHANGELOG.md`.
- Every feature or structural piece has its doc in `docs/`, with diagrams drawn with the
  `esquemas-svg` skill (rule `docs.md`).
- FastAPI dependencies as `Annotated[T, Depends(fn)]`.

## Non-obvious details

- SQLAlchemy resolves `Mapped[...]` annotations at runtime: model imports must not move under
  `TYPE_CHECKING` (ruff `TC001`-`TC003` and `UP037` are ignored for that reason).
- A model or handler module that is not imported in `app/db_registry.py` does not exist for
  `Base.metadata`, the dispatcher or the job registry.
- Migrations never run in the app lifespan; the `migrate` step runs them before the API.
- The test suite reads no `.env` file (`SETTINGS_ENV_FILE=""` in `tests/conftest.py`).
- `ENVIRONMENT` has no default: outside a test or a checkout with `.env.local`, the app does not
  import without it. Outside `local`, hosts, origins and trusted proxies must be set explicitly.
- A session dependency must be `Depends(get_session, scope="function")`: with the default scope
  the commit runs after the response is sent.
- `@limiter.limit(...)` goes under `@router...`; above it the route is not limited.
- Event handlers take `(payload, event_id)` and must raise unless the work was done.
- Fix a bug with a test that fails first; what a mocked session cannot show (what is stored, who
  may touch it, malformed input) is tested in `tests/integration/api/`.
- Tests of `app/core` must not import a context: the repository tests use
  `tests/integration/core/sample.py`.
- Rows that must not change under each other are read with `SELECT ... FOR UPDATE` first
  (`WorkshopRepo.get_for_update` returns a `LockedWorkshop`, the type the seat rules require).
- The pre-commit hook stashes unstaged changes and runs `uv run`, which syncs the venv to the
  stashed `pyproject.toml`: commit dependency changes first, in their own commit.

## Rules (`.claude/rules/`)

`api-endpoints`, `context-boundaries`, `migrations`, `tests`, `env-vars`, `docs`. Each ends with
how it is enforced. Guides worth reading first: `docs/workshops.md` (the example, pattern by
pattern), `docs/security.md` (authorization), `docs/operations.md`, `docs/deployment.md`.
