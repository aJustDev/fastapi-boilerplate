# Roadmap

Current state of the boilerplate and what comes next. Items are grouped by priority based on production impact. Contributions are welcome — pick any item, open an issue to discuss the approach, and submit a PR.

## Done

- [x] Bounded contexts with layers inside (router -> use case -> service -> repo -> model), enforced by import-linter
- [x] Async SQLAlchemy 2.x + asyncpg
- [x] Domain exception hierarchy with global HTTP handlers
- [x] CORS configuration
- [x] Alembic migrations (async env, reference data as migrations, drift test)
- [x] Health check endpoints (used by Docker and scheduled jobs)
- [x] JWT auth with access + refresh tokens, Argon2 hashing, permission guards
- [x] Repository pattern with offset + cursor pagination and field filtering
- [x] Unit and integration test structure
- [x] Docker + docker-compose
- [x] Pre-commit hooks (ruff check + format)
- [x] Transactional Outbox event bus with PostgreSQL LISTEN/NOTIFY
- [x] Scheduled jobs claimed with a lease (multi-worker safe)
- [x] Configurable connection pool (`pool_size`, `max_overflow`, `pool_timeout` via env vars)
- [x] Structured JSON logging with per-request `request_id` tracing
- [x] Error contract (`{detail, code}`) published in OpenAPI
- [x] HTTP hardening: security headers, trusted hosts and proxies, database timeouts
- [x] Strict tooling: mypy, import-linter, pip-audit, hadolint, meta-tests
- [x] Docs per feature with generated diagrams; Claude Code rules and skills in `.claude/`

## P1 - Hardening

- [x] Rate limiting: a limit on every endpoint via slowapi (strict for auth, default for the rest), in memory per process
- [x] Observability (metrics) — Prometheus-compatible `/v1/metrics` endpoint with HTTP request metrics and DB pool gauges

## P2 - Nice to have

### Observability (traces)

OpenTelemetry tracing, off by default, with `trace_id` in the JSON logs, and Prometheus in
multiprocess mode for `--workers N`.

### Shared rate limit storage

A Redis or memcached storage for slowapi, so limits hold across processes and restarts.

### API versioning strategy

Document how to introduce `v2/` alongside `v1/` — router registration, schema coexistence, deprecation headers, and when to remove old versions.

### WebSocket support

Base pattern for real-time features: connection management, auth over WS, and integration with the event bus for push notifications.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and workflow. To work on a roadmap item:

1. Open an issue referencing the item to discuss scope and approach
2. Create a branch and implement following the project conventions
3. Submit a PR against `main`
