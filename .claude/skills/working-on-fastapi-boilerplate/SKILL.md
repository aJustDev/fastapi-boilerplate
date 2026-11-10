---
name: working-on-fastapi-boilerplate
description: Orientation and workflow for the FastAPI boilerplate. Use at the start of a session in this repo, and before writing code, adding a feature or a context, changing the schema or fixing a bug. Covers where things live, the layer and context rules, migrations, tests, docs with diagrams and the commit flow.
---

# Working on fastapi-boilerplate

## Orientation (read only)

1. `CLAUDE.md` is the always-on summary; the rules in `.claude/rules/` load with the files.
2. State, in parallel:
   - `git branch --show-current`, `git status --short`, `git log --oneline -5`
   - `gh pr list --state open --json number,title,headRefName,author --jq '.[] | "#\(.number) \(.author.login) \(.headRefName) \(.title)"'`
   - `gh run list --branch main --limit 3`
3. Do not touch code until the task is clear.

## Before coding

1. Read `docs/architecture.md` and the doc of the piece you will touch (index: `docs/README.md`).
2. Copy the closest existing pattern: `app/auth/` (services, rotation, own transaction on
   reuse), `app/items/` (plain CRUD with events).
3. Create a branch before the first change.

## While coding

- Router -> one use case -> services -> repos -> models; use cases orchestrate, services hold
  the rules. Contexts do not import each other; `app/core` imports no context.
- Register new models and handlers in `app/db_registry.py`.
- Domain exceptions with a `code`, never `HTTPException` below the router.
- A model change comes with its Alembic migration, reviewed by hand (`docs/migrations.md`).
- A new setting goes to `Settings` and `.env.example`.
- Tests at the right level, with a negative control for bug fixes (`docs/testing.md`).
- Update the doc of the piece, with diagrams from the `esquemas-svg` skill reviewed as PNG.

## Before committing

1. `bash scripts/ci-local.sh` (or `SKIP_INTEGRATION=1` without Docker) must be all green.
2. One line in `CHANGELOG.md` under `[Unreleased]` if the change is visible to users.
3. Commit dependency changes (`pyproject.toml`, `uv.lock`) first, in their own commit: the
   pre-commit hook stashes unstaged files and `uv run` syncs the venv to the stash.
4. English conventional commits, no trailers; PR to `main` with a short description.
