---
name: migrations
description: Alembic migrations. Review autogenerate drafts, real downgrades, no edits after apply, lock-safe changes on tables with data.
paths:
    - migrations/**
    - app/*/models/**
    - app/core/db.py
    - app/core/events/models.py
    - app/core/jobs/models.py
---

# Migrations

Guide: `docs/migrations.md`, decision: `docs/adr/002-alembic.md`.

- A model change needs its migration in the same PR: `uv run alembic revision --autogenerate
  --rev-id NNNN -m "..."`, then **read the draft**. Autogenerate misses renames (drop + add),
  data changes, `CONCURRENTLY`, `NOT VALID` and partial index predicates.
- `downgrade()` really undoes `upgrade()`.
- An applied migration is never edited: fix it with a new one.
- Reference data (roles, permissions, job rows) goes in migrations; development data in
  `scripts/seed_dev.py`.
- Tables with data: indexes `CONCURRENTLY` in an `autocommit_block`, FK and CHECK with
  `NOT VALID` then `VALIDATE`, renames and type changes in expand/contract steps. The running
  version must keep working against the new schema.
- Names follow the naming convention of `Base.metadata`; expression indexes get an explicit name.
- Defaults that exist in the database are declared with `server_default` in the model.

## Enforcement

- `tests/integration/test_migrations.py`: models equal to the migrated schema, and every
  migration down to base and up again.
- CI: a single Alembic head.
