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

## P0 — Production essentials

### Connection pool tuning

Expose `pool_size`, `max_overflow`, and `pool_timeout` in config. With `uvicorn --workers N` each process creates its own pool — without explicit limits it's easy to exhaust PostgreSQL's `max_connections`. Sensible defaults should work out of the box and scale with the number of workers.

### Structured logging with request tracing

Replace plain-text log output with JSON-formatted structured logging for production environments (keep human-readable format for local development). Add middleware that generates a unique `request_id` per request and injects it into every log line, making it possible to trace a single request across all layers. This is critical for debugging in production and integrates directly with log aggregators (ELK, Datadog, CloudWatch, Loki).

## P1 — Hardening

### Rate limiting

Add request throttling to protect public endpoints from abuse. `slowapi` (built on `limits`) supports in-memory, Redis, and other backends. The initial implementation should use in-memory storage to keep the zero-external-dependencies philosophy, with a clear path to swap in PostgreSQL for distributed deployments.

### Observability (metrics + tracing)

Expose application metrics (request latency, status codes, throughput per endpoint, active DB connections) via a `/metrics` endpoint compatible with Prometheus. Optionally integrate OpenTelemetry for distributed tracing. This enables monitoring dashboards and alerting — knowing something is degrading before users report it.

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
