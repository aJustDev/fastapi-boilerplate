# Logging

## Overview

The logging system provides two output modes selected automatically by environment:

- **Colored** (local/dev) — human-readable format with ANSI colors, layer and module labels
- **JSON** (production) — structured one-line JSON objects, ready for log aggregators (ELK, Datadog, CloudWatch, Loki)

Every HTTP request is assigned a unique `request_id` that is injected into every log line emitted during that request, enabling full end-to-end tracing across all layers.

## Configuration

| Variable | Default | Values | Description |
|----------|---------|--------|-------------|
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | Minimum log level for the `app` logger |
| `LOG_FORMAT` | `auto` | `auto`, `json`, `text` | Output format selection |

**`LOG_FORMAT` behavior:**

| Value | local/dev | Other environments |
|-------|-----------|-------------------|
| `auto` | Colored output | JSON output |
| `json` | JSON output | JSON output |
| `text` | Plain text (no color) | Plain text (no color) |

## Request tracing

### How it works

1. `RequestIdMiddleware` intercepts every HTTP request
2. If the client sends an `X-Request-ID` header, that value is used; otherwise a UUID4 hex string is generated
3. The ID is stored in a `ContextVar`, which is async-safe and automatically scoped to the current task
4. `RequestIdFilter` reads the `ContextVar` and injects `request_id` into every `LogRecord`
5. The `X-Request-ID` header is returned in the response

### Using the request ID

The `request_id` appears automatically in all log lines — no code changes needed. If you need to access it programmatically:

```python
from app.core.logging.context import get_request_id

rid = get_request_id()  # returns "" outside of a request context
```

### Client-side correlation

API gateways and frontend clients can pass their own `X-Request-ID` header to correlate logs across services:

```bash
curl -H "X-Request-ID: my-trace-123" http://localhost:8000/v1/items
```

The response will echo the same ID:

```
X-Request-ID: my-trace-123
```

## Log format examples

### Colored (development)

```
INFO: [Router] [Login] [a1b2c3d4e5f6...] ❯ Attempting login for user: john
INFO: [Service] [Auth] [a1b2c3d4e5f6...] ❯ Looking up user by email: john
INFO: [Repo] [User] [a1b2c3d4e5f6...] ❯ Executing get_by_email
```

### JSON (production)

```json
{"timestamp": "2024-03-22T10:15:23.456000+00:00", "level": "INFO", "layer": "Router", "module": "Login", "logger": "app.api.v1.auth", "request_id": "a1b2c3d4e5f67890abcdef1234567890", "message": "Attempting login for user: john"}
{"timestamp": "2024-03-22T10:15:23.458000+00:00", "level": "INFO", "layer": "Service", "module": "Auth", "logger": "app.services.auth", "request_id": "a1b2c3d4e5f67890abcdef1234567890", "message": "Looking up user by email: john"}
```

### JSON fields

| Field | Type | Description |
|-------|------|-------------|
| `timestamp` | string | ISO 8601 UTC timestamp |
| `level` | string | Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `layer` | string | Architectural layer (Router, UseCase, Service, Repo, Core, Deps, App) |
| `module` | string | Module name, title-cased (e.g., "Refresh Token") |
| `logger` | string | Full Python logger name (e.g., `app.services.auth`) |
| `request_id` | string | UUID4 hex or client-provided ID; empty for non-request contexts |
| `message` | string | Log message |
| `exception` | string | Full traceback (only present when logging an exception) |

## Architecture

### Component pipeline

```
LogRecord
  │
  ├─→ LayerModuleFilter    — extracts layer + module from logger path
  ├─→ RequestIdFilter      — injects request_id from ContextVar
  │
  └─→ Formatter
       ├─ ColoredFormatter  — ANSI colored output (local/dev)
       ├─ Formatter         — plain text with timestamp (text mode)
       └─ JSONFormatter     — single-line JSON (production)
```

### Key files

| File | Responsibility |
|------|---------------|
| `app/core/logging/config.py` | `setup_logging()`, `JSONFormatter`, dictConfig setup |
| `app/core/logging/filters.py` | `LayerModuleFilter`, `RequestIdFilter`, noise filters |
| `app/core/logging/context.py` | `ContextVar` for `request_id` |
| `app/core/logging/middleware.py` | `RequestIdMiddleware` (ASGI) |
| `app/core/middleware.py` | Middleware registration order |

## Filtering

Two built-in noise filters reduce log volume:

- **`IgnoreOptionsFilter`** — suppresses CORS preflight `OPTIONS` request logs
- **`IgnoreHealthcheckFilter`** — suppresses `/health/liveness` endpoint logs

To add a new filter:

1. Create a class in `app/core/logging/filters.py` extending `logging.Filter`
2. Return `False` to suppress the record, `True` to allow it
3. Register it in `setup_logging()` dictConfig under `"filters"` and add it to the relevant handler or logger

## Background workers

The `OutboxWorker` and `JobWorker` run outside of HTTP request context, so `request_id` is empty (`""`) in their logs. They are identified by:

- **Layer**: `Core`
- **Module**: `Worker` (outbox) or `Worker` (jobs)

Their logs are still structured as JSON in production and can be filtered by `layer` and `logger` fields.

## Integration with log aggregators

The JSON output is newline-delimited JSON (ndjson), which is natively supported by most log aggregators:

- **ELK Stack**: Filebeat can ingest ndjson directly; no Logstash parsing needed
- **Grafana Loki**: Use `json` stage in Promtail pipeline
- **Datadog**: Auto-parsed when log source is set to `python`
- **AWS CloudWatch**: JSON logs are automatically parsed into structured fields

Use the `request_id` field to correlate all log entries for a single request across your aggregator's search interface.
