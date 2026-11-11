# Testing

pytest with four levels, each split by context like `app/` (`auth/`, `workshops/`, `core/` for
infrastructure), plus meta-tests that check rules over the whole code base.

| Level | Directory | Tests | Database |
|---|---|---|---|
| Unit | `tests/unit/` | Services, use cases, repos and core modules in isolation | Mocked |
| Functional | `tests/functional/` | HTTP behavior through the real app and middleware: status, body, headers, auth | Mocked session |
| Integration | `tests/integration/` | SQL, workers, migrations | PostgreSQL 18 in a testcontainer |
| Integration, API | `tests/integration/api/` | Whole requests: HTTP, the real `get_session`, real SQL | The same container |

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
- `api_client` (same conftest) is an `httpx.AsyncClient` over the real app with nothing
  overridden: it points the app's own `async_session_factory` at the container, so a request
  runs the real `get_session` and commits. The rows a request can write are truncated after each
  test; reference data from the migrations stays. `tests/integration/api/helpers.py` has the
  steps every flow starts with (`register`, `login`, `signed_up`), and `workshops.py` the steps
  on the example context.
- Tests of the infrastructure do not depend on the example context. The repository and its
  pagination are tested against `SampleORM` (`tests/integration/core/sample.py`), a model of the
  tests' own whose table lives in a separate schema, created by the `sample_table` fixture: the
  tests that compare the models with the migrations look at `public` only.
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
- Integration, API: `tests/integration/api/` with the same `pytestmark` and `api_client`. This is
  the level for anything that depends on the request as a whole: what is stored after a 2xx, who
  may touch whose data, what a malformed input answers. A mocked session cannot show any of it.
- Concurrency: several requests at once with `asyncio.gather` over `api_client`. Each request
  gets its own connection, so they interleave in PostgreSQL like requests of different
  processes. Assert what must hold however they interleave, not an order
  (`tests/integration/api/test_workshop_concurrency.py`).
- Events stored by one transaction share its timestamp: find them by type, not by position.
- A test for a bug must fail against the code before the fix: run it once without the fix.

## Meta-tests

A test that scans the code has a `test_scanner_sees_...` canary that fails if it finds nothing to
check, and `test_detector_...` cases with the forms it must catch. Exemptions go in the list at
the top of the file, each with its reason, keyed by method and path where routes are listed.

| Test | Rule |
|---|---|
| `tests/functional/test_auth_required_on_all_endpoints.py` | Every route answers 401 without a token and to a token that is not one, except `PUBLIC` |
| `tests/integration/api/test_authorization.py` | No route with a path id serves the resource of another user |
| `tests/unit/test_every_endpoint_has_a_rate_limit.py` | Every endpoint is limited at its tier, and the route runs the limited function, except `EXEMPT` |
| `tests/unit/test_api_endpoint_single_use_case.py` | No function of a router module runs more than one use case |
| `tests/functional/test_error_contract.py` | Error bodies match the published schemas |
| `tests/functional/test_openapi_contract.py` | Each operation declares the errors it answers and is described |
| `tests/unit/test_no_interpolated_sql.py` | No SQL in `app/` is built from strings, directly or through a variable |
| `tests/unit/core/events/test_published_event_types_have_handlers.py` | Every published event type has a handler |
| `tests/integration/core/test_job_rows.py` | Every job handler has its row and every row its handler |
| `tests/unit/core/test_register_middleware.py` | Middleware stack and order; the paths exempt from the host check are the probes |
| `tests/functional/test_middleware_behaviour.py` | Hosts, origins and trusted proxies let through what the settings say |
| `tests/unit/core/test_env_example_sync.py` | `.env.example` lists every setting |
| `tests/unit/test_dockerfile_runtime_copy.py` | The image copies an allow-list |
| `tests/unit/test_release.py` | The newest version in `CHANGELOG.md` is the one in `pyproject.toml`, under an `[Unreleased]` section |
| `tests/integration/test_migrations.py` | Models match the migrations, CHECK constraints and index predicates included; downgrades work |

Meta-tests that walk the API use `tests/_routes.py` (`iter_api_routes`), not `app.routes`.

## Configuration

`pyproject.toml`: `asyncio_mode = "auto"`, `--strict-markers`, marker `integration`, deprecation
warnings raised from `app` or `tests` are errors, coverage `fail_under = 80` over `app/`.

## Guarantees and limits

- `TestClient` is banned by ruff (`TID251`): it runs the app in another thread and event loop.
- Functional tests do not run the lifespan: no workers, no database check.
- Integration tests need Docker; CI runners have it.
