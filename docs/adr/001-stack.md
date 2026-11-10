# 001. Base stack

- Status: accepted
- Date: 2026-11-10

## Context

The boilerplate is the starting point of new backends, which begin small and should grow to a
mid-size API without a change of infrastructure. Every component added on day one is one more
thing to run, secure and upgrade in every project built from it.

## Decision

| Concern | Choice |
|---|---|
| Language | Python 3.14 (latest stable) |
| HTTP framework | FastAPI with Pydantic v2 |
| Database access | SQLAlchemy 2.1 async ORM with asyncpg |
| Database | PostgreSQL, also used as message broker (transactional outbox with LISTEN/NOTIFY) and job scheduler (row claims with leases) |
| Auth | JWT (PyJWT) access and rotated refresh tokens, Argon2id passwords |
| Observability | Structured JSON logs with request ids, Prometheus metrics |
| Packaging | uv with a committed `uv.lock` |
| Quality | ruff (lint and format), mypy, pytest with testcontainers, pip-audit, hadolint |
| Delivery | Docker image built from an allow-list, docker compose for local work |

Versions are kept at the latest release; Dependabot proposes updates weekly.

## Alternatives considered

- **Redis or RabbitMQ for events, Celery for jobs**: more throughput, but a second stateful
  service to operate before any project needs it, and events could no longer commit atomically
  with the business change.
- **Sync SQLAlchemy**: simpler stack traces, but one blocked thread per in-flight query.
- **pip or Poetry**: uv resolves and installs much faster and its lockfile is what Dependabot and
  CI check.

## Consequences

- One database to back up and monitor; the event and job throughput is bounded by PostgreSQL,
  which is enough for the target size and documented in `docs/event-bus.md` and `docs/jobs.md`.
- Async everywhere: CPU-bound work (Argon2) must go through `run_blocking`.
- Staying on latest versions means absorbing breaking changes early (FastAPI 0.137 changed how
  included routers expose paths, see `docs/metrics.md`).
