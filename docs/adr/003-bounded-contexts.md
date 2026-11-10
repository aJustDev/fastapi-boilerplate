# 003. Light bounded contexts, use cases orchestrate services

- Status: accepted
- Date: 2026-11-10

## Context

Code was grouped only by layer (`app/models`, `app/repos`, `app/services`, ...). Every feature
touched six top-level folders, and nothing stopped one domain from importing another's internals,
so coupling between domains would grow unnoticed. Infrastructure in `app/core` also imported
domain code (ORM models, the item event handlers).

## Decision

- Group by context first, then by layer: `app/<context>/{models,schemas,repos,services,
  use_cases,api}` plus `event_handlers/` or `jobs/` when needed. Start with `auth` and `items`;
  create a new context only when its first entity arrives.
- `app/core` is infrastructure, including the ORM of the outbox and the jobs, and imports no
  context. `app/deps` holds the dependencies shared by every context.
- `app/db_registry.py` is the single place that imports models and handler modules.
- Use cases orchestrate (order of steps, which services, transactions of their own, events);
  services hold the business rules; plain CRUD may go from use case to repository.
- One use case per endpoint. Contexts reference each other by id, with no ORM relationship
  across them, and compose through events or a use case of the owning context.
- import-linter contracts and an AST test enforce it.

## Alternatives considered

- **Layers only**: simpler for a handful of entities, but the coupling it allows is invisible
  until it is expensive to undo.
- **Business rules in use cases** (as in the downstream project this was ported from): fewer
  files, but rules shared by two use cases end up duplicated or in one use case calling another.

## Consequences

- A feature lives in one folder; adding a context means a router line, registry imports and a
  contract update (see `docs/architecture.md`).
- `ItemORM.owner` (a relationship into `auth`) was removed: items expose `owner_id` only.
- Exceptions to the import rules must be written in `.importlinter` with a reason; if the same
  kind keeps appearing, this decision is revisited.
