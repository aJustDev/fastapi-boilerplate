# Testing

pytest with three levels, each split by context like `app/` (`auth/`, `items/`, `core/` for
infrastructure), plus meta-tests that check rules over the whole code base.

| Level | Directory | Tests | Database |
|---|---|---|---|
| Unit | `tests/unit/` | Services, use cases, repos and core modules in isolation | Mocked |
| Functional | `tests/functional/` | HTTP behavior through the real app and middleware: status, body, headers, auth | Mocked session |
| Integration | `tests/integration/` | SQL, workers, migrations | PostgreSQL 18 in a testcontainer |

## How it works

- `tests/conftest.py` sets `SETTINGS_ENV_FILE=""` before importing `app` (no `.env` file is read)
  and disables the rate limiter. It provides `mock_session`, `fake_user`, `auth_headers` and
  `client`, an `httpx.AsyncClient` over `ASGITransport` with `get_session` overridden.
- `tests/integration/conftest.py` starts one PostgreSQL container per session and builds the
  schema with `alembic upgrade head`. `db_session` is rolled back after each test (repositories
  only flush). `committing_factory` gives real commits on a `NullPool` engine for code that
  commits by itself (workers, separate transactions) and empties the tables listed by the
  module's `committing_tables` fixture before and after the test. `seed_user` inserts a user for
  foreign keys.
- Async fixtures and integration modules use `loop_scope="session"`, so the session-scoped engine
  and the tests share one event loop.

## Usage

```bash
uv run pytest                          # everything (Docker needed)
uv run pytest --ignore=tests/integration
uv run pytest tests/integration -m integration
uv run pytest --cov=app                # with coverage
```

- Unit: `tests/unit/<context>/test_<name>.py`; mock the collaborators with `AsyncMock`.
- Functional: `tests/functional/<context>/`; use `client`, patch repository methods where they are
  used (`app.auth.repos.user.UserRepo.get_by_id`), assert status, `code` and body.
- Integration: `tests/integration/<context>/` with
  `pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]`, a real
  repository on `db_session`.
- A test for a bug must fail against the code before the fix: run it once without the fix.

## Meta-tests

Each one has a `test_scanner_sees_...` canary that fails if it finds nothing to check. Exemptions
go in the list at the top of the file, each with its reason.

| Test | Rule |
|---|---|
| `tests/functional/test_auth_required_on_all_endpoints.py` | Every route answers 401 without a token, except `PUBLIC` |
| `tests/unit/test_every_endpoint_has_a_rate_limit.py` | Every endpoint declares a rate limit, except `EXEMPT` |
| `tests/unit/test_api_endpoint_single_use_case.py` | An endpoint runs at most one use case |
| `tests/functional/test_error_contract.py` | Error bodies match the published schemas |
| `tests/unit/test_no_interpolated_sql.py` | No SQL in `app/` is built from strings |
| `tests/unit/core/events/test_published_event_types_have_handlers.py` | Every published event type has a handler |
| `tests/unit/core/test_register_middleware.py` | Middleware stack and order |
| `tests/unit/core/test_env_example_sync.py` | `.env.example` lists every setting |
| `tests/unit/test_dockerfile_runtime_copy.py` | The image copies an allow-list |
| `tests/integration/test_migrations.py` | Models match the migrations; downgrades work |

Meta-tests that walk the API use `tests/_routes.py` (`iter_api_routes`), not `app.routes`.

## Configuration

`pyproject.toml`: `asyncio_mode = "auto"`, `--strict-markers`, marker `integration`, deprecation
warnings raised from `app` or `tests` are errors, coverage `fail_under = 80` over `app/`.

## Guarantees and limits

- `TestClient` is banned by ruff (`TID251`): it runs the app in another thread and event loop.
- Functional tests do not run the lifespan: no workers, no database check.
- Integration tests need Docker; CI runners have it.
