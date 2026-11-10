# Architecture

Code is grouped by what it is about (a bounded context: `auth`, `workshops`), and inside each
context by layer. A new feature touches one folder; the rules for what may import what are
written down and checked, so the structure does not erode as the project grows.

## Layout

```
app/
  core/            infrastructure: config, db (Base, mixins), repo.py (BaseRepo), schema.py,
                   security, events (bus, worker, outbox model), jobs (worker, model, heartbeat),
                   logging, metrics, middleware, rate limiting, exceptions, lifespan
  deps/            FastAPI dependencies shared by every context (session, repos, current user)
  api/v1/          composes the context routers, plus health and metrics
  auth/            context: users, roles, permissions, tokens
    models/ schemas/ repos/ services/ use_cases/ api/ jobs/
  workshops/       context: the example (docs/workshops.md)
    models/ schemas/ repos/ services/ use_cases/ api/ event_handlers/ jobs/ exceptions.py
  db_registry.py   imports every model and handler module (see below)
```

The packages form bands, and imports only go down them.

![Package layers](img/architecture-layers.svg)

Workshops gets the current user from `app.deps.auth`, never by importing `app.auth`; workshops
and users are linked by `organizer_id` and `attendee_id` only, without an ORM relationship across
contexts.

## How a request flows

The figure follows a request from the middleware to the commit.

![A request through the layers](img/architecture-request.svg)

| Layer | Does | Does not |
|---|---|---|
| `api/` | Parse HTTP, resolve dependencies, call **one** use case, return schemas | Business rules, queries |
| `use_cases/` | Orchestrate: order of steps, which services, own transactions when needed, events | Business rules |
| `services/` | Business rules, reusable by several use cases | FastAPI imports, `HTTPException` |
| `repos/` | Queries through `BaseRepo[T]`; `flush`, never `commit` | Business rules |
| `models/` | ORM tables | Queries, logic |
| `schemas/` | Request and response shapes | Logic, database access |

**Use cases orchestrate services; services hold the business rules.** A plain CRUD use case may
call the repository directly (`app/workshops/use_cases/create_workshop.py`); as soon as a rule
appears, it goes into a service (`app/workshops/services/`: who may act on which workshop, which
states follow which, who gets a seat). Errors are domain exceptions (`app/core/exceptions`, and
`exceptions.py` of a context for its own), turned into HTTP responses by global handlers.

## Rules and how they are enforced

| Rule | Enforced by |
|---|---|
| Inside a context, a layer imports only the layers below it | `.importlinter`, contract `layers` |
| `app.core` imports no context, `app.deps`, `app.api` or the registry | `.importlinter`, contract `core` |
| Contexts do not import each other | `.importlinter`, contracts `workshops-auth`, `auth-workshops` |
| An endpoint runs at most one use case | `tests/unit/test_api_endpoint_single_use_case.py` |
| The models match the migrations | `tests/integration/test_migrations.py` |
| A route does not serve the resource of another user | `tests/integration/api/test_authorization.py` |

`uv run lint-imports` runs the contracts; CI runs it on every PR. A justified exception goes in
`ignore_imports` with a comment; several of the same kind mean the rule needs revisiting.

## The registry

Models must be imported for `Base.metadata` to know their tables, and event and job handlers
must be imported for their decorators to register them. `app/db_registry.py` imports all of
them, and `main.py`, `migrations/env.py` and the integration tests import the registry. It sits
outside `app/core` because it imports the contexts. A handler module that is not listed there
never runs: the event bus then retries its events until they fail (see `docs/event-bus.md`).

## Adding a context

1. `app/<context>/` with the layers it needs (`models/ schemas/ repos/ services/ use_cases/
   api/`, plus `event_handlers/` or `jobs/`), each with an `__init__.py`. Every module of a
   context is in one of those layers; its own exceptions may go in `app/<context>/exceptions.py`.
2. Models on `app.core.db.Base` with `IntPkMixin`/`AuditMixin`; repositories on `BaseRepo[T]`;
   request schemas with the bounded types of `app/core/schema.py`.
3. Router in `app/<context>/api/router.py`, included in `app/api/v1/__init__.py`. Each route
   gets a permission guard, a rate limit and the error responses it can answer; anything
   addressed by id gets an ownership check in its use case (`docs/security.md`).
4. Imports of its models and handlers in `app/db_registry.py`.
5. In `.importlinter`: the context in the `containers` of the `layers` contract, and a
   `forbidden` contract against each other context. A context that takes the current user from
   `app.deps` needs `allow_indirect_imports = true` in its contract against `app.auth`, like
   `workshops-auth`: `app.deps.auth` imports the user model.
6. A migration for its tables, its permissions and the roles that get them, and the rows of its
   jobs (`docs/migrations.md`).
7. Tests in `tests/{unit,functional,integration}/<context>/`, requests in
   `tests/integration/api/`, and its resources in `RESOURCES` of
   `tests/integration/api/test_authorization.py`.
8. A doc in `docs/` if it brings a new piece of infrastructure or a non-obvious flow.

To add a feature to an existing context, add files to its layers; nothing outside the context
changes except the registry, the router composition or the migrations.

## Replacing the example context

`app/workshops` is there to be read and then removed. `auth` and `core` do not know it, so
removing it is a list of deletions, in this order:

1. **Code.** Delete `app/workshops/`, its four imports in `app/db_registry.py`, its two routers
   in `app/api/v1/__init__.py`, and in `.importlinter` its line in the `layers` containers, its
   line in the `core` contract and the contracts `workshops-auth` and `auth-workshops`.
2. **Schema.** A new migration that drops `enrollments` and `workshops`, deletes the
   `workshops:*` permissions (their grants go with them) and the rows of the jobs
   `workshop_reminders` and `workshops_finish`. `migrations/versions/0009_drop_items.py` did
   the same for the example that came before. Earlier migrations stay as they are.
3. **Its tests.** Delete `tests/unit/workshops/`, `tests/functional/workshops/`,
   `tests/integration/workshops/`, `tests/_workshops.py`, and in `tests/integration/api/` the
   files `workshops.py`, `test_workshop_flows.py` and `test_workshop_concurrency.py`.
4. **Tests of the infrastructure that travel through its routes.** They need a route to go
   through, and the example provides it: point them at a route of the new context.
   - In `tests/integration/api/`: `test_transactions.py`, `test_audit_trail.py`,
     `test_error_inputs.py`, `test_pagination.py`, and `test_authorization.py` (its `RESOURCES`
     say how to create a private resource for each path parameter).
   - In `tests/functional/`: three requests in `test_error_contract.py`, the paths named in
     `test_openapi_contract.py`, the templated path in `test_metrics_endpoint.py`.
   - The canaries, which name an endpoint or an event of the example or expect at least as
     many routes as it had: `tests/unit/test_api_endpoint_single_use_case.py`,
     `tests/unit/test_every_endpoint_has_a_rate_limit.py`,
     `tests/unit/core/events/test_published_event_types_have_handlers.py`,
     `tests/functional/test_auth_required_on_all_endpoints.py`,
     `tests/functional/test_openapi_contract.py`.
   - `tests/conftest.py`: the permission `fake_user` lacks (`workshops:moderate`).

   The tests of the repository, the event bus and the workers use a model of their own
   (`tests/integration/core/sample.py`) and do not change.
5. **The rest.** `scripts/seed_dev.py`, `docs/workshops.md` and its figure, the paths of
   `.claude/rules/context-boundaries.md`, the example bodies of the error responses in
   `app/core/exceptions/schemas.py`, and the examples in `README.md`, `CLAUDE.md` and `docs/`
   that name a workshop route.

Then add the first real context with the list above. `bash scripts/ci-local.sh` says what was
missed: a contract that still names the package, a job row left without its handler and a
canary that finds too few routes each fail by name.

## Cross-cutting pieces

- **Event bus**: transactional outbox with LISTEN/NOTIFY. See `docs/event-bus.md`.
- **Scheduled jobs**: rows claimed with a lease. See `docs/jobs.md`.
- **Auth**: rotated refresh tokens, revocation, roles and permissions. See `docs/auth.md`.
- **Database and migrations**: `docs/database.md`, `docs/migrations.md`.
- **Logging, metrics**: `docs/logging.md`, `docs/metrics.md`. Log lines carry the layer and
  module taken from the logger name (`app.workshops.api.router` logs as `[Router] [Workshops]`).
- **Configuration, tooling, Docker**: `docs/configuration.md`, `docs/tooling.md`, `docs/docker.md`.

Decisions behind this layout: [ADR-003](adr/003-bounded-contexts.md).
