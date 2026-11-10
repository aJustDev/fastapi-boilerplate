# Changelog

All notable changes to this boilerplate. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

Each PR that changes behavior adds one line under `[Unreleased]`, in the section that fits
(Added, Changed, Fixed, Removed, Security), with the PR number. Typos and invisible refactors do
not count.

## [Unreleased]

### Added

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

- `app/deps/database.py`, an unused re-export of `get_session` (#24).
- `AUDIT-CHECKLIST.md` (its open items are done or in `ROADMAP.md`) and `docs/skill.md` (now the `working-on-fastapi-boilerplate` skill).
- `ItemORM.owner`, a relationship across contexts; items expose `owner_id`.
- `sql/` (schema, deltas, seeds and their shell scripts), replaced by the migrations.

### Fixed

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
