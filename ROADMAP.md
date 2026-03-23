# Roadmap

Current state of the boilerplate and what comes next. Items are grouped by priority based on production impact. Contributions are welcome — pick any item, open an issue to discuss the approach, and submit a PR.

## Done

- [x] Layered architecture (router → use case → service → repo → model)
- [x] Async SQLAlchemy 2.x + asyncpg
- [x] Domain exception hierarchy with global HTTP handlers
- [x] CORS configuration
- [x] SQL-first migrations (schema, deltas, seeds)
- [x] Health check endpoints (used by Docker and scheduled jobs)
- [x] JWT auth with access + refresh tokens, Argon2 hashing, permission guards
- [x] Repository pattern with offset + cursor pagination and field filtering
- [x] Unit and integration test structure
- [x] Docker + docker-compose
- [x] Pre-commit hooks (ruff check + format)
- [x] Transactional Outbox event bus with PostgreSQL LISTEN/NOTIFY
- [x] Scheduled jobs with FOR UPDATE SKIP LOCKED (multi-worker safe)
- [x] Configurable connection pool (`pool_size`, `max_overflow`, `pool_timeout` via env vars)
- [x] Structured JSON logging with per-request `request_id` tracing

## P1 — Hardening

- [x] Rate limiting — Two-tier throttling via slowapi (strict for auth, default for general endpoints) with in-memory storage
- [x] Observability (metrics) — Prometheus-compatible `/v1/metrics` endpoint with HTTP request metrics and DB pool gauges

## P2 — Nice to have

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
