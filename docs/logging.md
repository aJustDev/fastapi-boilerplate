# Logging

Standard library logging configured once, when the app is built (`setup_logging()` in
`create_app()`), with two output modes: colored text for local work and one-line JSON for log
aggregators. Every request leaves one access line; every line logged while serving it carries
its `request_id`, and every line carries the architectural layer and module of the logger.

## How it works

- `RequestIdMiddleware` takes `X-Request-ID` from the request when it is a plain token (letters,
  digits, `.`, `_`, `-`, at most 64 characters) and generates a UUID4 hex otherwise, stores it in
  a `ContextVar` for the duration of the request and returns it in the response header.
- `RequestIdFilter` adds `request_id` to every record (empty outside a request: jobs, startup).
  The text formats print it in brackets only when there is one.
  An event handler logs under the id of the request that published its event
  (`docs/event-bus.md`).
- `LayerModuleFilter` derives `layer` and `module` from the logger name: the first of `api`,
  `use_cases`, `services`, `repos`, `core`, `deps` in it gives the layer (`Router`, `UseCase`,
  `Service`, `Repo`, `Core`, `Deps`, else `App`) and the last part the module, title-cased. A
  context router is named after its context: `app.workshops.api.router` logs as `[Router] [Workshops]`.
- The formatter is chosen from `ENVIRONMENT` and `LOG_FORMAT`:

| `LOG_FORMAT` | `local`/`dev` | other environments |
|---|---|---|
| `auto` | colored text | JSON |
| `json` | JSON | JSON |
| `text` | colored text | plain text |

- `AccessLogMiddleware` writes the access line once the response is sent:
  `GET /v1/workshops/7 404 not_found 3ms` (method, path, status, the `code` of the error body
  when there is one, time to answer), colored by status on a color terminal. In JSON the same
  facts are fields of `http`, with the client address. The path is the raw one, without the
  query string: the client writes the query, and it can carry search terms, emails or tokens; a
  `%0A` stays encoded and cannot start a new line. Probes, the metrics scrape and CORS
  preflights leave no line (`QUIET_PATHS`). Uvicorn's own access log is off.
- The exception handlers name the error code of the response with `record_error_code()`, which
  the access line reads. What they log themselves depends on whose error it is:

| Error | Level | Line |
|---|---|---|
| A 4xx the API answers as designed (not found, forbidden, invalid credentials, validation) | DEBUG | `NotFoundError: Workshop not found (ID: 7) (app/workshops/services/access.py:45 in ensure_visible())` |
| Rate limit | WARNING | `Rate limit 5 per 1 minute exceeded by 203.0.113.7 on POST /v1/auth/login, retry in 56s` |
| A value or a race the database stopped | WARNING | the class, SQLSTATE and constraint, never the values (`docs/errors.md`) |
| A 5xx: a domain error of ours, an unhandled exception | ERROR | one line, `Unhandled RuntimeError: boom (app/...:12 in f(), GET /v1/x)`, with the traceback |

  The place is the last line of `app/` in the traceback, not the library or mock below it.
  slowapi's own warning is silenced: the handler's line says the same and when to retry.

## Usage

```python
import logging

logger = logging.getLogger(__name__)  # app.<context>.<layer>.<module>
logger.info("Workshop %s created", workshop.id)  # lazy %-formatting (ruff rule G)
```

`get_request_id()` (`app/core/logging/context.py`) returns the current id, for example to pass it
to an external call. Clients and gateways can send their own `X-Request-ID` to correlate logs
across services.

A JSON line:

```json
{"timestamp": "2026-03-22T10:15:23.458000+00:00", "level": "DEBUG", "layer": "Service", "module": "Auth", "logger": "app.auth.services.auth", "request_id": "a1b2c3d4e5f67890abcdef1234567890", "message": "Looking up user credentials"}
```

Fields: `timestamp` (ISO 8601, UTC), `level`, `layer`, `module`, `logger`, `request_id`,
`message`, and `exception` (the traceback) when one was logged. A record logged with
`extra={"fields": {...}}` adds those keys to its line, without replacing a standard one: the
startup log puts its facts in `startup` (`docs/operations.md`).

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Level of the `app` loggers; uvicorn stays at INFO (where it listens, startup, shutdown) |
| `LOG_FORMAT` | `auto` | `auto`, `json` or `text` |

## Guarantees and limits

- Output is newline-delimited on stdout; shipping it (Loki, ELK, CloudWatch...) is the platform's
  job.
- One handler, on the root logger: the `app` loggers at `LOG_LEVEL`, uvicorn at INFO and every
  other library at WARNING reach it by propagation, so every line has the same format.
- Uvicorn imports the app before its first line, so a process started as `uvicorn main:app`
  (the image) logs in that format from the first line. With `--reload` or `--workers` the
  parent process never imports the app: its own lines stay in uvicorn's format.
- A request that is not traffic (another probe, a scrape) is silenced by adding its path to
  `QUIET_PATHS` in `app/core/logging/middleware.py`; nothing else drops access lines.
- A client-supplied request id that is not a plain token is replaced, so it cannot inject text
  into the log lines or the response headers.
- Database errors are logged without their bound parameters (`hide_parameters` on the engine):
  the statement is in the log, the values (emails, password hashes) are not.

## Files

| File | Role |
|---|---|
| `app/core/logging/config.py` | `setup_logging()`, `JSONFormatter`, `ansi_enabled()`, `json_enabled()` |
| `app/core/logging/filters.py` | Layer/module and request id filters |
| `app/core/logging/context.py` | `request_id` `ContextVar` |
| `app/core/logging/middleware.py` | `RequestIdMiddleware`, `AccessLogMiddleware`, `QUIET_PATHS` |
