# Errors

Every error response has the same JSON shape with a stable machine-readable `code`, produced by
global exception handlers, and the shape is published in OpenAPI. Clients branch on `code`;
`detail` is human text and may change.

```json
{"detail": "Item not found (ID: 42)", "code": "not_found"}
{"detail": "Validation error", "code": "validation_error", "errors": ["body.name: Field required"]}
```

## How it works

`app/core/exceptions/handlers.py` registers one handler per error family:

| Source | Status | `code` |
|---|---|---|
| `NotFoundError` | 404 | `not_found` |
| `ConflictError` | 409 | `conflict` |
| `BusinessValidationError` / `UseCaseException` | 400 | `business_validation` / `use_case_error` |
| `InvalidCursorError` | 400 | `invalid_cursor`: a pagination cursor this API did not issue |
| `AuthenticationError` | 401 | `unauthenticated`, with `WWW-Authenticate: Bearer` |
| `RefreshTokenReuseError` | 401 | `refresh_token_reused` |
| `AuthorizationError` | 403 | `forbidden` |
| Request validation | 422 | `validation_error`; per-field messages in `errors` |
| `IntegrityError`: duplicate key, broken reference | 409 | `integrity_conflict` |
| `IntegrityError`: NOT NULL or CHECK violation | 422 | `invalid_input`; same shape as `validation_error` |
| Other `DBAPIError` for a value the column cannot take (SQLSTATE class 22, or refused by asyncpg) | 422 | `invalid_input` |
| Rate limit exceeded | 429 | `rate_limited`; `Retry-After` in seconds |
| `HTTPException` (unknown route, wrong method...) | its status | `not_found`, `method_not_allowed`, ... |
| Any other exception | 500 | `internal_error`; the message is logged, never returned |

Domain exceptions declare `status_code` and `code` as class attributes. `main.py` declares
`ErrorResponse` and `ValidationErrorResponse` (`app/core/exceptions/schemas.py`,
`extra="forbid"`) for every operation.

## Usage

Raise domain exceptions from services and use cases; never `HTTPException` below the router:

```python
from app.core.exceptions import ConflictError, NotFoundError

if await self.user_repo.get_by_email(email):
    raise ConflictError("User", "email already registered")
```

A new error type subclasses the closest one and sets its code:

```python
class OutOfStockError(BusinessValidationError):
    code = "out_of_stock"
```

Check uniqueness in the service to give a precise error; the `integrity_conflict` handler covers
the race between that check and the `INSERT`.

Request schemas use the bounded types of `app/core/schema.py` (`ShortText`, `LongText`, `Int32`,
`IdPath`, `PageQuery`, `SearchQuery`...) instead of bare `str` and `int`, so a value a column
cannot hold (too long, a NUL character, out of range) is a `validation_error` with the field
name. `invalid_input` is the net under them: it means a field reached the database unbounded,
and its log line (class, SQLSTATE and constraint, never the values) says which.

## Guarantees and limits

- `tests/functional/test_error_contract.py` validates every registered handler and real requests
  against the schemas, fails when a handler is added without being checked, and checks the
  OpenAPI references.
- A 500 never exposes the exception message; the traceback goes to the log with the request id.
- An exception no handler knows is answered by `UnhandledErrorMiddleware`
  (`app/core/exceptions/middleware.py`), the innermost middleware. The 500 is built inside the
  stack, so it has the CORS, security and `X-Request-ID` headers of any other response and is
  logged once. The handler registered for `Exception` only sees what a middleware itself raises.
- `code` values are part of the API contract: renaming one is a breaking change.
