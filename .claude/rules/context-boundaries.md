---
name: context-boundaries
description: Bounded contexts and layers. What may import what, cross-context references by id, the registry, adding a context.
paths:
    - app/auth/**
    - app/items/**
    - app/core/**
    - app/db_registry.py
    - .importlinter
---

# Context boundaries

Guide: `docs/architecture.md`, decision: `docs/adr/003-bounded-contexts.md`.

- Inside a context, a layer imports only the layers below it:
  `api | event_handlers | jobs` > `use_cases` > `services` > `repos` > `models | schemas`.
- `app.core` is infrastructure: it imports no context, no `app.deps`, no `app.api` and not the
  registry. Domain code (handlers, jobs, exceptions of a context) lives in its context.
- Contexts do not import each other. They reference each other by id (FK without an ORM
  relationship) and react to each other through events. Shared request needs (current user,
  repositories) go through `app.deps`.
- Every model and every handler module is imported in `app/db_registry.py`, and nowhere else
  for registration purposes.
- Use cases orchestrate services; services hold the business rules; plain CRUD may call the
  repository from the use case.
- A new context: layers with `__init__.py`, router in `app/api/v1`, imports in the registry, and
  `.importlinter` updated (add it to the `layers` containers and a `forbidden` contract against
  each other context, with `allow_indirect_imports = true` against `app.auth` if it uses
  `app.deps`). Every module of a context is a layer; its exceptions go in `exceptions.py`.

## Enforcement

`uv run lint-imports` (contracts in `.importlinter`, run in CI). An exception goes in
`ignore_imports` with a comment explaining why.
