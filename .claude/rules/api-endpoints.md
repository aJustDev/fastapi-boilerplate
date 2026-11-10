---
name: api-endpoints
description: Routers and shared dependencies. One use case per endpoint, auth unless public, a rate limit on every endpoint, domain exceptions for errors.
paths:
    - app/*/api/**
    - app/api/**
    - app/deps/**
---

# API endpoints

Guide: `docs/architecture.md`, `docs/security.md`, `docs/errors.md`.

- An endpoint parses HTTP, resolves dependencies, calls **one** use case and returns a schema
  (`response_model`). No business rules, no queries. Two steps that belong together are a
  composed use case, or an event and a handler.
- Dependencies as `Annotated[T, Depends(fn)]`; repositories through `get_repo(RepoClass)`.
- Authenticated by default. A public route is a decision: add it to `PUBLIC` in
  `tests/functional/test_auth_required_on_all_endpoints.py` with the reason.
- Authorized at two levels: the route depends on a permission guard
  (`Annotated[User, Depends(require_permissions(permission="<context>:<action>"))]`), and the use
  case checks ownership of anything addressed by id (404 for someone else's resource). Plain
  `CurrentUser` is only for routes about the caller itself. Lists filter by owner in the query.
- Every endpoint has `@limiter.limit(settings.RATE_LIMIT_DEFAULT)` (or `RATE_LIMIT_STRICT` for
  unauthenticated auth endpoints) under the `@router...` decorator, and a `request: Request`
  parameter, which slowapi needs.
- Errors are domain exceptions from `app.core.exceptions`; never `HTTPException` from services or
  repos. A new error type sets its `code`.
- A new context router is included in `app/api/v1/__init__.py`.

## Enforcement

- `tests/unit/test_api_endpoint_single_use_case.py` (AST: at most one `.execute(` per endpoint)
- `tests/functional/test_auth_required_on_all_endpoints.py` (anonymous and bad-token request to
  every route)
- `tests/integration/api/test_authorization.py` (a second user on every route with a path id)
- `tests/unit/test_every_endpoint_has_a_rate_limit.py`
- `tests/functional/test_error_contract.py`

To unblock one of them: add the entry to its allow-list with the reason next to it, never to
silence it. More than a couple of entries of the same kind means the rule needs revisiting.
