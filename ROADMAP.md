# Roadmap

Current state of the boilerplate and what comes next. Contributions are welcome — pick any item, open an issue to discuss the approach, and submit a PR.

## Done

- [x] Bounded contexts with layers inside (router -> use case -> service -> repo -> model), enforced by import-linter
- [x] Async SQLAlchemy 2.x + asyncpg, with the commit as part of the request
- [x] Domain exception hierarchy with global HTTP handlers; unhandled errors answered inside the middleware stack
- [x] CORS configuration
- [x] Alembic migrations (async env, reference data as migrations, drift test)
- [x] Health endpoints that follow the database, exempt from the host check
- [x] JWT auth with access + single-use refresh tokens, reuse detection, Argon2 hashing
- [x] Authorization: a permission on every route, ownership on every resource, tested with two users
- [x] Repository pattern with offset + cursor pagination and declared filters
- [x] Tests at four levels (unit, functional, integration, whole requests on PostgreSQL) and meta-tests
- [x] Docker (multi-stage, non-root, pinned by digest) + docker-compose
- [x] Pre-commit hooks (ruff check + format); `main` protected, CI required
- [x] Transactional Outbox event bus with PostgreSQL LISTEN/NOTIFY, daily cleanup and replay command
- [x] Scheduled jobs claimed with a lease (multi-worker safe)
- [x] Configurable connection pool (`pool_size`, `max_overflow`, `pool_timeout` via env vars)
- [x] Structured JSON logging with per-request `request_id` tracing, carried into event handlers
- [x] Error contract (`{detail, code}`) declared per route in OpenAPI
- [x] HTTP hardening: security headers, trusted hosts and proxies, bounded input, database timeouts
- [x] Fail-closed configuration: no default environment, validators outside local
- [x] Rate limiting: a limit on every endpoint via slowapi (strict for auth, default for the rest), in memory per process
- [x] Prometheus-compatible `/v1/metrics`: HTTP, DB pool and outbox metrics
- [x] Operations: `python -m app.cli` (first admin, outbox, worker process), deployment guide
- [x] Strict tooling: mypy, import-linter, pip-audit, hadolint, image build and scan in CI
- [x] An example context that uses every piece: workshops with seats, a waiting list, events and jobs
- [x] Docs per feature with generated diagrams; Claude Code rules and skills in `.claude/`

## Next


### Observability (traces)

OpenTelemetry tracing, off by default, with `trace_id` in the JSON logs, and Prometheus in
multiprocess mode for `--workers N`.

### Shared rate limit storage

Limits that hold across processes and restarts. slowapi is barely maintained and offers Redis
or memcached; a limiter with a PostgreSQL store would keep the stack to one database.

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
