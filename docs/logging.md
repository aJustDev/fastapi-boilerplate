# Logging

Standard library logging configured once at startup (`setup_logging()`), with two output modes:
colored text for local work and one-line JSON for log aggregators. Every line logged while
serving a request carries its `request_id`, and every line carries the architectural layer and
module of the logger.

## How it works

- `RequestIdMiddleware` takes `X-Request-ID` from the request when it is a plain token (letters,
  digits, `.`, `_`, `-`, at most 64 characters) and generates a UUID4 hex otherwise, stores it in
  a `ContextVar` for the duration of the request and returns it in the response header.
- `RequestIdFilter` adds `request_id` to every record (empty outside a request: workers, jobs,
  startup).
- `LayerModuleFilter` derives `layer` and `module` from the logger name: the first of `api`,
  `use_cases`, `services`, `repos`, `core`, `deps` in it gives the layer (`Router`, `UseCase`,
  `Service`, `Repo`, `Core`, `Deps`, else `App`) and the last part the module, title-cased. A
  context router is named after its context: `app.items.api.router` logs as `[Router] [Items]`.
- The formatter is chosen from `ENVIRONMENT` and `LOG_FORMAT`:

| `LOG_FORMAT` | `local`/`dev` | other environments |
|---|---|---|
| `auto` | colored text | JSON |
| `json` | JSON | JSON |
| `text` | plain text | plain text |

- The `uvicorn.access` logger drops OPTIONS requests, `/v1/health/liveness` and `/v1/metrics`.
  The filters compare the method and the path of the access record, never its text: the query
  string is written by the client and must not be able to hide a request.
- Exception handlers build a multi-line message (exception, location, request, status) and add
  color only when `ansi_enabled()`, so JSON lines never contain escape codes.

## Usage

```python
import logging

logger = logging.getLogger(__name__)  # app.<context>.<layer>.<module>
logger.info("Item %s created", item.id)  # lazy %-formatting (ruff rule G)
```

`get_request_id()` (`app/core/logging/context.py`) returns the current id, for example to pass it
to an external call. Clients and gateways can send their own `X-Request-ID` to correlate logs
across services.

A JSON line:

```json
{"timestamp": "2026-03-22T10:15:23.458000+00:00", "level": "DEBUG", "layer": "Service", "module": "Auth", "logger": "app.auth.services.auth", "request_id": "a1b2c3d4e5f67890abcdef1234567890", "message": "Looking up user credentials"}
```

Fields: `timestamp` (ISO 8601, UTC), `level`, `layer`, `module`, `logger`, `request_id`,
`message`, and `exception` (the traceback) when one was logged.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Level of the `app` loggers; uvicorn stays at WARNING and its access log at INFO |
| `LOG_FORMAT` | `auto` | `auto`, `json` or `text` |

## Guarantees and limits

- Output is newline-delimited on stdout; shipping it (Loki, ELK, CloudWatch...) is the platform's
  job.
- Third-party loggers propagate to the root logger, at WARNING.
- A new noise filter goes in `app/core/logging/filters.py` (return `False` to drop the record) and
  is registered in the `dictConfig` of `setup_logging()`. It decides on `_access_request(record)`
  (method and path), like the existing ones.
- A client-supplied request id that is not a plain token is replaced, so it cannot inject text
  into the log lines or the response headers.
- Database errors are logged without their bound parameters (`hide_parameters` on the engine):
  the statement is in the log, the values (emails, password hashes) are not.

## Files

| File | Role |
|---|---|
| `app/core/logging/config.py` | `setup_logging()`, `JSONFormatter`, `ansi_enabled()` |
| `app/core/logging/filters.py` | Layer/module, request id and noise filters |
| `app/core/logging/context.py` | `request_id` `ContextVar` |
| `app/core/logging/middleware.py` | `RequestIdMiddleware` |
