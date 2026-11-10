# Changelog

All notable changes to this boilerplate. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

Each PR that changes behavior adds one line under `[Unreleased]`, in the section that fits
(Added, Changed, Fixed, Removed, Security), with the PR number. Typos and invisible refactors do
not count.

## [Unreleased]

### Added

- Docs: deployment guide (required settings, migrations, first admin, what goes in front of the API) (#26).
- CI `image` job: builds the image, checks that it refuses to start unconfigured and that it becomes healthy with production settings. The daily audit also scans the image for vulnerabilities with a fix (#26).
- OpenAPI: each route declares the errors it answers (401, 403, 404, 409, 429 with `Retry-After`), endpoints and request fields are described, and the health and filter responses are typed (#26).
- A context may keep its exceptions in `app/<context>/exceptions.py` (layers contract) (#26).
- `python -m app.cli`: `create-admin`, `outbox replay`, `outbox cleanup` and `worker` (the outbox and job workers without the API). `OUTBOX_WORKER_ENABLED` and `JOB_WORKER_ENABLED` turn them off in the API process (#25).
- `outbox_cleanup` daily job, and counters `outbox_events_processed_total` and `outbox_events_failed_total` (#25).
- `DOCS_ENABLED` (off by default; Swagger UI, ReDoc and `/openapi.json`) and `METRICS_TOKEN` (bearer token for `/v1/metrics`) (#25).
- `created_by` and `updated_by` record the authenticated user; events carry the request id as `correlation_id` and their handlers log under it (#25).
- Docs: operations guide (health endpoints, command line, running the workers) (#25).
- API test level, `tests/integration/api/`: requests through the real app and the real `get_session` against PostgreSQL. It covers the session model, authorization with two users, malformed input and pagination across pages (#24).
- Authorization in the example context: each `items` route requires a permission, the use case checks the owner, lists are limited to the caller, and `items:manage` lifts the limit. Registration assigns the `user` role (#24).
- Bounded input types in `app/core/schema.py` (`ShortText`, `LongText`, `Int32`, `IdPath`, `PageQuery`, `SearchQuery`...) and error codes `invalid_cursor` (400) and `invalid_input` (422) (#24).
- Claude Code configuration: `CLAUDE.md`, path-scoped rules in `.claude/rules/`, read-only permissions in `.claude/settings.json`, the `working-on-fastapi-boilerplate` skill; `docs/README.md` index.
- Error contract: every error body is `{detail, code}` with a stable code, the schemas are published in OpenAPI, and `IntegrityError` answers 409 instead of 500.
- Security headers middleware, `TrustedHostMiddleware`, `ProxyHeadersMiddleware`, and startup validators for hosts, origins and trusted proxies outside local.
- Statement, lock and command timeouts plus pool recycling on every database connection; startup fails outside local if the process is not in UTC.
- Meta-tests: auth required on every route, a rate limit on every endpoint, error contract, no interpolated SQL, every published event has a handler, middleware order.
- Docs: errors and HTTP security guides.
- Alembic migrations: async `env.py`, baseline equal to the previous SQL schema, reference data as a migration, `migrate` compose service, drift and round-trip tests; `scripts/seed_dev.py` for development data.
- Hourly `revoked_tokens_cleanup` job (#14).
- `scripts/install-hooks.sh` (pre-commit and a pre-push hook that blocks pushes to `main`) and `scripts/ci-local.sh`.
- mypy, pip-audit, hadolint and a generated-diagrams check in CI; daily dependency audit workflow.
- Docs: configuration, tooling and Docker guides; ADRs in `docs/adr/`.

### Changed

- `fastapi` without the `standard` extra, plus `python-multipart` and `email-validator`: 46 runtime packages instead of 78 (#26).
- Outside local `ALLOWED_ORIGINS` must be set; `[]` is valid for an API that no browser calls (#26).
- Compose: the `db` service takes its credentials from the env file the API reads; PostgreSQL, Prometheus and Grafana are published on loopback only (#26).
- The base image is pinned by digest with Debian security updates applied at build time; GitHub Actions are pinned by commit; workflows declare `permissions: contents: read`; `main` is a protected branch (#26).
- Meta-tests: the SQL scanner follows variables and more calls; rate limits are checked for tier and for the decorator really wrapping the route; public and exempt routes are listed by method and path; the drift test compares CHECK constraints and index predicates (#26).
- Event handlers receive `(payload, event_id)`, and their retry state is keyed by module and qualified name. Events pending during the upgrade run their handlers once more (#25).
- `OUTBOX_MAX_RETRIES` defaults to 12 (a little over an hour of retries) instead of 5 (about 30 s) (#25).
- Outside local `FORWARDED_ALLOW_IPS` must be set (empty for no proxy), and uvicorn runs with `--no-proxy-headers` (#25).
- The health endpoints are exempt from `ALLOWED_HOSTS`, and a rejected `Host` answers JSON with code `invalid_host` (#25).
- `outbox_events.aggregate_id` and `correlation_id` are text (#25).
- `ENVIRONMENT` has no default: the app does not start until it is set. The Docker image sets `ENVIRONMENT=production` (#24).
- Sessions end by counter: `users.session_version` replaces `tokens_valid_after`, tokens carry it as the `sv` claim and the unused `scopes` claim is gone. Tokens issued before the upgrade are rejected (#24).
- Password hashes use the argon2-cffi defaults and are upgraded at login when they were made with older parameters (#24).
- `username` accepts 3-50 letters, digits, `.`, `_` and `-`; `password` at most 128 characters (#24).
- Code grouped by bounded context (`app/auth`, `app/items`) with layers inside; infrastructure ORM in `app/core`; `app/db_registry.py` registers models and handlers; import-linter contracts and a one-use-case-per-endpoint test enforce the boundaries.
- PostgreSQL 18 in compose and in the integration tests (volume `pgdata18`).
- Python 3.14 and every dependency on its latest release (FastAPI 0.162, SQLAlchemy 2.1).
- Dev dependencies live in the `dev` dependency group (`uv sync`, no `--extra dev`).
- The Docker image copies an allow-list (`main.py`, `app/`), runs in UTC and ships without pip.
- `APP_VERSION` is read from the installed package.
- Outside `local`, `SECRET_KEY` must have at least 32 bytes.
- Dependabot uses the `uv` ecosystem, so its PRs update `uv.lock`.

### Removed

- The `ROOT_PATH` setting (`FastAPI(root_path=...)` is deprecated): give the prefix to the server with `uvicorn --root-path` (#26).
- Unused schemas `UserCreate` and `PermissionRead` (#26).
- `SlowAPIMiddleware`: it does nothing for routes of an included router; the endpoint decorators are the rate limit (#25).
- The partial index `ix_users_is_active` (#25).
- `app/deps/database.py`, an unused re-export of `get_session` (#24).
- `AUDIT-CHECKLIST.md` (its open items are done or in `ROADMAP.md`) and `docs/skill.md` (now the `working-on-fastapi-boilerplate` skill).
- `ItemORM.owner`, a relationship across contexts; items expose `owner_id`.
- `sql/` (schema, deltas, seeds and their shell scripts), replaced by the migrations.

### Fixed

- The first command of the quick start failed on a fresh clone: compose needs `.env.local` and no step created it (#26).
- A `DB_PASSWORD` changed in `.env.local` reached the API and not the database container (#26).
- Deprecation warnings raised in integration tests were not turned into errors (missing `tests/integration/__init__.py`) (#26).
- Docs: jobs do not use `SKIP LOCKED`, `LOG_FORMAT=text` is colored in local, FastAPI changed router flattening in 0.137, and other statements the code did not back (#26).
- Two event handlers with the same function name shared one retry state: when one failed and the other succeeded, the event was marked processed and the failed handler never ran again (#25).
- The example webhook handler reported a 500 from the receiver as a delivery, so it was never retried (#25).
- An instance that started while the database was unreachable never became ready and never started its workers (#25).
- The image's `HEALTHCHECK` failed with the explicit `ALLOWED_HOSTS` production requires (#25).
- Offset pagination repeated and skipped rows when the sort column had ties, and a page past the end reported `total: 0` (#25).
- The text filter treated `%` and `_` as wildcards, and any model attribute worked as a filter (#25).
- Nothing scheduled the outbox cleanup, and `FAILED` events could only be replayed from a Python shell (#25).
- A database password with `@`, `/` or `#` was parsed as part of the host; `sslmode=` in `DATABASE_URL` failed on the first connection (#25).
- The startup banner was printed by one process per database, so later processes and deployments never showed it (#25).
- A job handler without its row in `scheduled_jobs`, or a row without a handler, never ran and nothing said so (#25).
- Any registered user could read, change and delete the items of every other user (#24).
- A deployment without `ENVIRONMENT` ran as `local` and accepted the placeholder `SECRET_KEY`, which lets anyone sign tokens (#24).
- Responses were sent before the transaction committed: a failed commit still answered 2xx, and a read right after a write could miss it (#24).
- A replayed refresh token did not end the session of whoever had used it first in the same second (#24).
- Unhandled errors answered a 500 without CORS headers, security headers or request id, and logged the traceback twice (#24).
- NUL characters, out-of-range integers, oversized text and forged pagination cursors ended as 500s, some without a login; a client request id that was not UTF-8 broke any request (#24).
- Cursor pagination failed on the second page when sorting by `created_at` (#24).
- `IntegrityError` answered 409 for NOT NULL and CHECK violations; they are a 422 (#24).
- Database errors logged their bound values, password hashes included, and the message of PostgreSQL with the offending key (#24).
- A query string containing `/v1/metrics` or `/health/liveness` removed the request from the access log, and the client request id was logged verbatim (#24).
- Revocations were purged at `exp`, 30 s before the token stops being accepted (#24).
- Startup without a reachable database hung for 60 s (and ignored Ctrl+C) while the banner retried the connection; connections now time out after `DB_CONNECT_TIMEOUT`.
- `OUTBOX_MAX_RETRIES` is applied to published events (#22).
- `RATE_LIMIT_DEFAULT` was documented but applied to no endpoint; `Retry-After` held the word `minute` instead of seconds.
- ORM models now declare the database defaults, partial and case-insensitive indexes and CHECK constraints that only the SQL schema had.
- Outbox events were dispatched more than once with several workers; NOTIFY now wakes the worker (#13).
- Events with no registered handler were marked processed and lost (#13).
- Jobs could run twice with several workers, and a starting worker reset jobs other workers were running (#13).
- Metrics labeled unmatched requests with their raw path (unbounded cardinality) (#13).
- ANSI color codes inside JSON logs (#13).
- `.env.local` was copied into the Docker image (#13).
- Refresh tokens were not rotated, logout left the refresh token valid, and a replayed refresh token went unnoticed (#14).
- Login response time revealed whether an account exists (#14).
- Email and username lookups were case-sensitive while their unique indexes are not (#14).
- The 30 s JWT leeway was ignored (#14).
