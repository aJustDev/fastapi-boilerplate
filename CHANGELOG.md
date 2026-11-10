# Changelog

All notable changes to this boilerplate. Format based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

Each PR that changes behavior adds one line under `[Unreleased]`, in the section that fits
(Added, Changed, Fixed, Removed, Security), with the PR number. Typos and invisible refactors do
not count.

## [Unreleased]

### Added

- Alembic migrations: async `env.py`, baseline equal to the previous SQL schema, reference data as a migration, `migrate` compose service, drift and round-trip tests; `scripts/seed_dev.py` for development data.
- Hourly `revoked_tokens_cleanup` job (#14).
- `scripts/install-hooks.sh` (pre-commit and a pre-push hook that blocks pushes to `main`) and `scripts/ci-local.sh`.
- mypy, pip-audit, hadolint and a generated-diagrams check in CI; daily dependency audit workflow.
- Docs: configuration, tooling and Docker guides; ADRs in `docs/adr/`.

### Changed

- Code grouped by bounded context (`app/auth`, `app/items`) with layers inside; infrastructure ORM in `app/core`; `app/db_registry.py` registers models and handlers; import-linter contracts and a one-use-case-per-endpoint test enforce the boundaries.
- PostgreSQL 18 in compose and in the integration tests (volume `pgdata18`).
- Python 3.14 and every dependency on its latest release (FastAPI 0.162, SQLAlchemy 2.1).
- Dev dependencies live in the `dev` dependency group (`uv sync`, no `--extra dev`).
- The Docker image copies an allow-list (`main.py`, `app/`), runs in UTC and ships without pip.
- `APP_VERSION` is read from the installed package.
- Outside `local`, `SECRET_KEY` must have at least 32 bytes.
- Dependabot uses the `uv` ecosystem, so its PRs update `uv.lock`.

### Removed

- `ItemORM.owner`, a relationship across contexts; items expose `owner_id`.
- `sql/` (schema, deltas, seeds and their shell scripts), replaced by the migrations.

### Fixed

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
