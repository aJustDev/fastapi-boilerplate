---
name: tests
description: Test levels, fixtures, meta-tests with canaries, negative control, no TestClient.
paths:
    - tests/**
    - pyproject.toml
---

# Tests

Guide: `docs/testing.md`.

- Levels: `unit/` (no I/O), `functional/` (HTTP through the app with `httpx.AsyncClient` +
  `ASGITransport`, database mocked), `integration/` (real PostgreSQL 18 via testcontainers, schema
  from `alembic upgrade head`), and `integration/api/` (whole requests with `api_client`: the
  real `get_session` on that database). Each split by context; infrastructure under `core/`.
- What a mocked session cannot show goes in `integration/api/`: what is stored after a 2xx, who
  may touch whose data, what malformed input answers, what holds under simultaneous requests.
- Tests of `app/core` do not import a context: use `tests/integration/core/sample.py`.
- `db_session` rolls back after each test; code that commits by itself (workers, anything that
  must survive a request rollback) uses `committing_factory` and overrides `committing_tables`.
- `TestClient` is banned (ruff `TID251`): it runs the app in another thread and event loop.
- Patch at the place of use (`app.auth.repos.user.UserRepo.get_by_id`), with the new paths.
- A meta-test (a rule over the whole code base) has a `test_scanner_sees_...` canary and
  `test_detector_...` cases for the forms it must catch; without them, a refactor can make it
  pass on zero cases or miss a variant. Walk routes with `tests/_routes.py`, not
  `app.routes`.
- Negative control: a test written for a bug must fail against the code before the fix. Check it
  once before trusting it.
- Assert on the error `code`, not on the message text.

## Enforcement

`--strict-markers`, deprecations from `app`/`tests` are errors, coverage `fail_under = 80`, ruff
`TID251`.
