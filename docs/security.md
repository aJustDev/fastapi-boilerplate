# HTTP security

The middleware stack and per-endpoint guards that every request goes through: trusted proxies
and hosts, security headers, CORS, authentication and rate limits.

## How it works

![Request path through the security layers](img/security-stack.svg)

`app/core/middleware.py` registers, from outermost to innermost: `ProxyHeadersMiddleware`,
`TrustedHostMiddleware`, metrics, request id, `SlowAPIMiddleware`, `SecurityHeadersMiddleware`,
CORS and GZip. The order is checked by `tests/unit/core/test_register_middleware.py`.

- **Proxies.** `X-Forwarded-For` and `X-Forwarded-Proto` are honored only from the addresses in
  `FORWARDED_ALLOW_IPS`, so the client IP seen by the rate limiter and the logs cannot be forged.
- **Hosts.** A `Host` header not in `ALLOWED_HOSTS` gets 400.
- **Headers.** Every response gets `Content-Security-Policy: default-src 'none';
  frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`,
  and `Strict-Transport-Security` when `HSTS_ENABLED`. `/docs`, `/redoc` and `/openapi.json` skip
  the CSP (Swagger UI loads scripts from a CDN). Headers the app already set are kept.
- **CORS.** Credentials allowed for `ALLOWED_ORIGINS`; methods GET, POST, PUT, PATCH, DELETE,
  OPTIONS; headers `Authorization`, `Content-Type`, `X-Request-ID`; `X-Request-ID` exposed.
- **Authentication.** Endpoints depend on `CurrentUser` (`docs/auth.md`).
- **Rate limits.** Each endpoint declares `@limiter.limit(...)`: `RATE_LIMIT_STRICT` on login,
  register and refresh, `RATE_LIMIT_DEFAULT` on the rest. It is checked when the endpoint is
  called, after its dependencies, so a request with an invalid token gets 401 and does not count.

## Usage

- A new endpoint gets `user: CurrentUser` and `@limiter.limit(settings.RATE_LIMIT_DEFAULT)` (with a
  `request: Request` parameter, which slowapi needs).
- A public endpoint is added to `PUBLIC` in `tests/functional/test_auth_required_on_all_endpoints.py`
  with the reason; an endpoint without a limit, to `EXEMPT` in
  `tests/unit/test_every_endpoint_has_a_rate_limit.py`.
- Behind a reverse proxy that already adds the security headers, set
  `SECURITY_HEADERS_ENABLED=false`.

## Configuration

| Setting | Default | Outside local |
|---|---|---|
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Proxy address or subnet; `*` aborts startup |
| `ALLOWED_HOSTS` | `["*"]` | Explicit host names; `*` or empty aborts startup |
| `ALLOWED_ORIGINS` | localhost frontends | Explicit origins; `*` or empty aborts startup |
| `SECURITY_HEADERS_ENABLED` | `true` | |
| `HSTS_ENABLED`, `HSTS_MAX_AGE` | `false`, `31536000` | Enable behind HTTPS |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_STRICT`, `RATE_LIMIT_DEFAULT` | `5/minute`, `60/minute` | |

## Guarantees and limits

- Every route answers 401 without a token unless listed in `PUBLIC`, and every endpoint has a
  limit unless listed in `EXEMPT`; both are checked by tests that walk the whole API.
- Rate limit counters are in memory per process: with `--workers N` the effective limit is `N`
  times the configured one, and they reset on restart. A shared limit needs a Redis or memcached
  storage for slowapi.
- Related safeguards: `SECRET_KEY` and UTC checks at startup (`docs/configuration.md`), no SQL
  built from strings (`tests/unit/test_no_interpolated_sql.py`), dependency audit
  (`docs/tooling.md`).

## Files

| File | Role |
|---|---|
| `app/core/middleware.py` | Stack and order |
| `app/core/security/headers.py` | `SecurityHeadersMiddleware` |
| `app/core/ratelimit.py` | `limiter` |
| `app/core/config.py` | Settings and their validators |
