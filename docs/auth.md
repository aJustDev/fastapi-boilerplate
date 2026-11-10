# Authentication and authorization

Stateless JWT authentication with short-lived access tokens and single-use refresh tokens, a
revocation list, per-account session invalidation, and role/permission guards. Every route
requires an access token except the ones explicitly public (`docs/security.md`).

## How it works

![Token lifecycle](img/auth-tokens.svg)

| Endpoint | Input | Result |
|---|---|---|
| `POST /v1/auth/register` | JSON: `email`, `username` (3-50 letters, digits, `.`, `_`, `-`), `password` (8-128 chars), `full_name` | 201 with the user |
| `POST /v1/auth/login` | OAuth2 form: `username` (email or username), `password` | Access and refresh token |
| `POST /v1/auth/refresh` | JSON: `refresh_token` | A new pair; the presented refresh token is revoked |
| `POST /v1/auth/logout` | Bearer access token; optional JSON `refresh_token` | 204; revokes both |
| `GET /v1/auth/me` | Bearer access token | The current user |

On every authenticated request `get_current_user` (`app/deps/auth.py`) checks that the token is
a valid `access` token, its `jti` is not revoked, the user exists and is active, and the token's
session version (claim `sv`) is the account's current `users.session_version`.

**Refresh rotation and reuse.** Each refresh token works once: `RevokedTokenRepo.revoke` is an
`INSERT ... ON CONFLICT DO NOTHING`, so of two requests with the same token only one succeeds.
A token that was already used raises `RefreshTokenReuseError` (401, code `refresh_token_reused`)
and `RefreshTokenUseCase` adds one to `users.session_version` in its own transaction, so it
survives the rollback of the failing request. Every token issued so far carries the previous
version and stops working, the pair handed out a moment before the replay included: whoever used
the stolen token first loses the session too. The user logs in again.

**Login.** An unknown account still verifies the password against a dummy Argon2 hash, so the
response time does not reveal which accounts exist. Email and username are matched
case-insensitively, like their unique indexes. Hashing runs in the thread pool
(`run_blocking`, `app/core/concurrency.py`). A username cannot contain `@`, so it can never be
mistaken for another account's email. The login form is bounded in the service: an identifier or
a password longer than registration allows, or with a NUL character, is a 401 before any query.

## Usage

```python
from app.deps.auth import CurrentUser, require_permissions

@router.get("/items")
async def list_items(request: Request, user: CurrentUser): ...

@router.delete("/items/{item_id}", dependencies=[Depends(require_permissions(permission="items:delete"))])
async def delete_item(...): ...
```

Users have roles (`user_roles`) and roles have permissions (`role_permissions`); the reference
roles `admin` and `user` and their permissions come from the migrations.
`require_permissions(role=...)` or `(permission=...)` answers 403 (`forbidden`) when missing.

## Configuration

| Setting | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | placeholder | HS256 key; outside local it must be set and at least 32 bytes |
| `ALGORITHM` | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token lifetime |
| `RATE_LIMIT_STRICT` | `5/minute` | Limit of login, register and refresh |

## Guarantees and limits

- Tokens carry `sub`, `type`, `sv` (session version), `jti`, `iat` and `exp`; `exp` is checked
  with 30 s of leeway for clock skew. Roles and permissions are not in the token: they are read
  from the database on every request, so a change applies at once.
- Revocations live in `revoked_tokens` until the token would be rejected as expired anyway (`exp`
  plus the leeway); the `revoked_tokens_cleanup` job deletes them hourly.
- Logout without the refresh token leaves that refresh token valid until it expires.
- Two clients refreshing with the same token at the same time (two tabs) look like a reuse and
  end the session: clients must serialize refreshes.
- Ending the sessions of an account is a counter, not a timestamp: no token issued before it
  survives, whatever its second. Tokens issued without an `sv` claim are rejected.
- Argon2id with the argon2-cffi defaults (RFC 9106 low-memory profile). A hash made with older
  parameters is replaced at its owner's next successful login (`needs_rehash`), and a stored
  value that is not an Argon2 hash is a failed login, not an error.

## Files

| File | Role |
|---|---|
| `app/auth/api/router.py` | Auth endpoints |
| `app/auth/services/auth.py` | Login, register, refresh, logout, session invalidation |
| `app/auth/use_cases/refresh_token.py` | Refresh and the separate transaction on reuse |
| `app/auth/repos/user.py`, `app/auth/repos/revoked_token.py` | Lookups, invalidation, revocation |
| `app/auth/jobs/revoked_tokens_cleanup.py` | Hourly purge of expired revocations |
| `app/core/security/jwt.py`, `app/core/security/password.py` | Tokens and Argon2 |
| `app/deps/auth.py` | `get_current_user`, `CurrentUser`, `require_permissions` |
