# Testing

Three-layer strategy: unit, functional, and integration. Each layer covers a distinct concern.

## Test layers

| Layer | Directory | What it tests | DB | Speed |
|-------|-----------|---------------|----|-------|
| Unit | `tests/unit/` | Services, use cases, repos, core modules in isolation | Mocked (`AsyncMock`) | ~3s |
| Functional | `tests/functional/` | HTTP contract: status codes, response shapes, auth, validation | Mocked (`AsyncMock`) | ~1s |
| Integration | `tests/integration/` | SQL correctness: CRUD, pagination, filtering, constraints | Real PostgreSQL via testcontainers | ~12s |

### When to use each layer

- **Unit**: testing business logic, branching, error paths. Mock all dependencies.
- **Functional**: testing that endpoints return the right status codes, shapes, and headers. Mock the DB session.
- **Integration**: testing that generated SQL is correct against real PostgreSQL. No mocks -- repos receive a real `AsyncSession`.

## Running tests

```bash
# All tests
uv run python -m pytest

# By layer
uv run python -m pytest tests/unit/
uv run python -m pytest tests/functional/
uv run python -m pytest tests/integration/

# Skip integration (no Docker required)
uv run python -m pytest -m "not integration"

# Only integration
uv run python -m pytest -m integration

# With coverage
uv run python -m pytest --cov=app --cov-report=term-missing
```

## Coverage

Minimum threshold: **80%** (configured in `pyproject.toml` under `[tool.coverage.report]`).

CI enforces this automatically via `--cov=app` -- the build fails if coverage drops below 80%.

## Markers

| Marker | Description |
|--------|-------------|
| `integration` | Requires Docker. Starts a PostgreSQL container via testcontainers. |

Registered in `pyproject.toml` under `[tool.pytest.ini_options]`.

## Fixtures

### Shared (`tests/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `fake_user` | function | `MagicMock(spec=UserORM)` with realistic test data |
| `auth_headers` | function | JWT bearer token headers for authenticated requests |
| `mock_session` | function | `AsyncMock` with commit, rollback, flush, execute, etc. |
| `client` | function | `httpx.AsyncClient` with ASGI transport and mocked DB session |

### Integration (`tests/integration/conftest.py`)

| Fixture | Scope | Description |
|---------|-------|-------------|
| `pg_container` | session | Starts `postgres:16-alpine` via testcontainers. One container per test session. |
| `pg_url` | session | Async connection URL from the container. |
| `async_engine` | session | SQLAlchemy async engine. Runs `Base.metadata.create_all` once. |
| `session_factory` | session | `async_sessionmaker` bound to the test engine. |
| `db_session` | function | `AsyncSession` that is rolled back after each test. |
| `seed_user` | function | Inserts a `UserORM` record for tests that need a valid `owner_id` FK. |

### Isolation pattern

Each integration test gets a fresh `AsyncSession`. After the test, `session.rollback()` discards all changes. This works because repos call `flush()` -- never `commit()` -- so all writes stay in the uncommitted transaction.

```
Session scope:  pg_container --> async_engine --> create_all (DDL once)
Function scope: db_session --> yield session --> rollback
```

No truncation, no manual cleanup. Rollback is faster and guarantees isolation.

### Event loop

Integration tests use `loop_scope="session"` on async fixtures and `pytest.mark.asyncio(loop_scope="session")` on test modules. This ensures the session-scoped engine and the function-scoped tests share the same event loop, avoiding `asyncpg` "different loop" errors.

## Adding new tests

### New unit test

1. Create file in `tests/unit/<module>/test_<name>.py`
2. Use `mock_session`, `fake_user`, or local `AsyncMock` fixtures
3. Test one behavior per function

### New functional test

1. Create file in `tests/functional/<module>/test_<name>_endpoint.py`
2. Use the `client` fixture to make HTTP requests
3. Patch repo methods with `unittest.mock.patch`
4. Assert status codes and response JSON

### New integration test

1. Create file in `tests/integration/repos/test_<name>_repo.py`
2. Add the `pytestmark` line at the top:
   ```python
   pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]
   ```
3. Use `db_session` fixture to get a real `AsyncSession`
4. Use `seed_user` if your model has a FK to `users`
5. Instantiate the repo directly: `repo = MyRepo(db_session)`

### Dependencies

Integration tests require Docker running on the host. GitHub Actions `ubuntu-latest` runners have Docker pre-installed.

Test dependencies in `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
    "pytest-cov>=6.0",
    "ruff>=0.11",
    "testcontainers[postgres]>=4.0",
]
```
