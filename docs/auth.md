# Authentication and Authorization

JWT-based auth with access + refresh tokens, token revocation, RBAC, and rate limiting.

## Token flow

1. **Login** `POST /v1/auth/login` -- accepts `application/x-www-form-urlencoded` (OAuth2 form). Returns `access_token` + `refresh_token`.
2. **Access** -- include `Authorization: Bearer <access_token>` on protected endpoints. Validated on every request via `get_current_user` dependency.
3. **Refresh** `POST /v1/auth/refresh` -- exchange a valid refresh token for a new token pair.
4. **Logout** `POST /v1/auth/logout` -- revokes the current access token. Requires `Authorization` header.
5. **Register** `POST /v1/auth/register` -- creates a new user. Email validated with `EmailStr`, password requires min 8 characters.
6. **Me** `GET /v1/auth/me` -- returns the current user profile.

## JWT structure

Every token (access and refresh) contains:

| Claim    | Description                          |
|----------|--------------------------------------|
| `sub`    | User ID (string)                     |
| `type`   | `"access"` or `"refresh"`            |
| `scopes` | Role names (empty for refresh)       |
| `jti`    | Unique token ID (UUID) for revocation|
| `exp`    | Expiration timestamp                 |
| `iat`    | Issued-at timestamp                  |

Defaults: access tokens expire in 30 min, refresh tokens in 7 days. Configurable via `ACCESS_TOKEN_EXPIRE_MINUTES` and `REFRESH_TOKEN_EXPIRE_DAYS`.

## Token revocation

Revoked tokens are stored in the `revoked_tokens` table (PostgreSQL):

```
revoked_tokens (jti UUID PK, expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ)
```

- On logout, the token's `jti` is inserted with its `expires_at`.
- On every authenticated request, `get_current_user` checks `is_revoked(jti)` -- a single PK index lookup.
- On refresh, the refresh token's `jti` is also checked.
- Expired entries can be cleaned up periodically with: `DELETE FROM revoked_tokens WHERE expires_at < now()`.

## Password hashing

Argon2 via `argon2-cffi` with tuned parameters (time_cost=2, memory=64KB, parallelism=2).

## RBAC and PBAC

- Users have roles (many-to-many via `user_roles`).
- Roles have permissions (many-to-many via `role_permissions`).
- Use `require_permissions(role="admin")` or `require_permissions(permission="items:write")` as FastAPI dependencies.

## Rate limiting

Auth endpoints (`/login`, `/register`, `/refresh`) use a strict rate limit (`RATE_LIMIT_STRICT`, default `5/minute`). General endpoints use `RATE_LIMIT_DEFAULT` (`60/minute`).

## Security configuration

| Variable                     | Default                    | Notes                                      |
|------------------------------|----------------------------|--------------------------------------------|
| `SECRET_KEY`                 | `change-me-in-production`  | **Must** be changed in non-local envs      |
| `ALGORITHM`                  | `HS256`                    | JWT signing algorithm                      |
| `ACCESS_TOKEN_EXPIRE_MINUTES`| `30`                       | Access token TTL                           |
| `REFRESH_TOKEN_EXPIRE_DAYS`  | `7`                        | Refresh token TTL                          |
| `RATE_LIMIT_STRICT`          | `5/minute`                 | Auth endpoint throttle                     |
| `RATE_LIMIT_DEFAULT`         | `60/minute`                | General endpoint throttle                  |

The app refuses to start in non-local environments if `SECRET_KEY` is still the default value.

## Key files

| File                               | Purpose                              |
|------------------------------------|--------------------------------------|
| `app/core/security/jwt.py`         | Token creation, decoding, TokenPayload|
| `app/core/security/password.py`    | Argon2 hashing/verification          |
| `app/deps/auth.py`                 | `get_current_user`, `require_permissions`|
| `app/services/auth.py`             | Login, register, refresh, logout logic|
| `app/repos/auth/revoked_token.py`  | Token revocation persistence         |
| `app/models/auth/revoked_token.py` | RevokedTokenORM model                |
| `app/api/v1/auth.py`               | Auth router endpoints                |
| `app/schemas/auth/token.py`        | Request/response schemas             |
| `app/core/config.py`               | SECRET_KEY validation                |
