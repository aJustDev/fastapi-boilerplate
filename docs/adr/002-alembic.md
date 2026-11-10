# 002. Schema migrations with Alembic

- Status: accepted
- Date: 2026-11-10

## Context

The schema lived in `sql/schema.sql` plus numbered deltas applied by a shell script, while the
code used SQLAlchemy ORM models. Three sources described the same tables (schema, deltas, models)
and nothing checked that they agreed: the integration tests built their database with
`create_all` from the models, so a delta could be missing or wrong without any test noticing.
`apply.sh` also recorded a delta as applied even when psql failed.

## Decision

- Alembic owns the schema. Revisions live in `migrations/versions/`, numbered (`0001_...`).
- `migrations/env.py` is async and reads `settings.DATABASE_URL`; tests pass an open connection.
- Revision `0001` reproduces the previous SQL schema exactly; `0002` holds the reference data.
- Migrations run as a separate step (`migrate` service, a release job), never in the app lifespan.
- Integration tests build the database with `alembic upgrade head`, and a test fails when the
  models and the migrated schema differ or when a downgrade does not undo its upgrade.
- CI fails with more than one head.

## Alternatives considered

- **Keep plain SQL, fix `apply.sh`**: no tooling to learn, but the models and the SQL would still
  drift apart silently.
- **`create_all` at startup**: no history, no downgrades, and no way to change an existing table.

## Consequences

- One source of truth for the schema, checked by tests in both directions.
- Autogenerate drafts most migrations, but they must be reviewed: it misses renames, data changes
  and lock-sensitive statements (see `docs/migrations.md`).
- Databases created with the old scripts must be recreated: constraint names changed.
