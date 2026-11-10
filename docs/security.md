# HTTP security

## What it solves

The API is reachable by anyone who can open a socket to it. Before a request reaches an
endpoint it must come from a host the API serves, carry the real client address, respect a
rate limit and, unless the route is public, a valid token. Every response carries headers that
stop browsers from misusing it.

## The path of a request

`app/core/middleware.py` registers the stack in a fixed order, checked by
`tests/unit/core/test_register_middleware.py`. The figure follows a request through it.

![Request path through the security layers](img/security-stack.svg)

## Proxies and hosts

| Setting | Default | Outside local |
|---|---|---|
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | The reverse proxy address or subnet; `*` is rejected at startup |
| `ALLOWED_HOSTS` | `["*"]` | The exact host names; `*` or an empty list is rejected |
| `ALLOWED_ORIGINS` | localhost frontends | The exact frontend origins; `*` or empty is rejected |

`ProxyHeadersMiddleware` (uvicorn) reads `X-Forwarded-For` and `X-Forwarded-Proto` only from the
addresses in `FORWARDED_ALLOW_IPS`. With `*`, any client could pick the IP that the rate limiter
and the logs see. `TrustedHostMiddleware` answers 400 to any other `Host` header.

CORS allows credentials, the usual methods and the `Authorization`, `Content-Type` and
`X-Request-ID` headers, and exposes `X-Request-ID` to the browser.

## Security headers

`SecurityHeadersMiddleware` (`app/core/security/headers.py`) adds to every response:

| Header | Value |
|---|---|
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Permissions-Policy` | camera, microphone, geolocation... disabled |
| `Strict-Transport-Security` | only with `HSTS_ENABLED=true` (HTTPS deployments), `HSTS_MAX_AGE` |

The docs pages (`/docs`, `/redoc`, `/openapi.json`) skip the CSP: Swagger UI loads its scripts
from a CDN. Headers the app already set are kept. Set `SECURITY_HEADERS_ENABLED=false` only when
a reverse proxy adds them.

## Rate limits

Each endpoint declares its limit with `@limiter.limit(...)` (slowapi, in memory per process):

- `RATE_LIMIT_STRICT` (`5/minute`) on the unauthenticated auth endpoints (login, register,
  refresh);
- `RATE_LIMIT_DEFAULT` (`60/minute`) on everything else;
- health and metrics are exempt.

`tests/unit/test_every_endpoint_has_a_rate_limit.py` fails if an endpoint has none. The limit
runs inside the endpoint, after its dependencies: an invalid token is rejected with 401 before it
counts. The counters live in each process, so with `--workers N` the effective limit is `N`
times the configured one and it resets on restart; for a shared limit, configure slowapi with a
Redis or memcached storage.

## Authentication

Every route answers 401 without a valid token except the ones listed in `PUBLIC` in
`tests/functional/test_auth_required_on_all_endpoints.py`, which sends a real anonymous request
to every other route. Tokens, rotation and revocation are described in `docs/auth.md`.

## Other safeguards

- Startup aborts outside local with a placeholder or short `SECRET_KEY` (`docs/configuration.md`)
  or a process time zone other than UTC.
- No SQL is built from strings: `tests/unit/test_no_interpolated_sql.py`.
- `pip-audit` runs on every PR and daily (`docs/tooling.md`).
