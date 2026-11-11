# HTTP security

The middleware stack and per-endpoint guards that every request goes through: trusted proxies
and hosts, security headers, CORS, authentication and rate limits.

## How it works

![Request path through the security layers](img/security-stack.svg)

`app/core/middleware.py` registers, from outermost to innermost: `ProxyHeadersMiddleware`,
request id, access log (`docs/logging.md`), `TrustedHostMiddleware`, metrics,
`SecurityHeadersMiddleware`, CORS, GZip and `UnhandledErrorMiddleware` (`docs/errors.md`). The order is checked by
`tests/unit/core/test_register_middleware.py`.

- **Proxies.** `X-Forwarded-For` and `X-Forwarded-Proto` are honored only from the addresses in
  `FORWARDED_ALLOW_IPS`, so the client IP seen by the rate limiter and the logs cannot be forged.
  The app's middleware is the only layer that reads them: uvicorn runs with `--no-proxy-headers`
  (the image does), because its own copy takes the list from the process environment alone.
- **Hosts.** A `Host` header not in `ALLOWED_HOSTS` gets 400 (`invalid_host`). The two health
  endpoints are exempt: a container health check asks for `localhost` and an orchestrator for
  the address of the instance, and a probe returns nothing a forged Host could abuse
  (`app/core/security/trusted_host.py`).
- **Headers.** Every response gets `Content-Security-Policy: default-src 'none';
  frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, a restrictive `Permissions-Policy`,
  and `Strict-Transport-Security` when `HSTS_ENABLED`. `/docs`, `/redoc` and `/openapi.json` skip
  the CSP (Swagger UI loads scripts from a CDN). Headers the app already set are kept.
- **CORS.** Credentials allowed for `ALLOWED_ORIGINS`; methods GET, POST, PUT, PATCH, DELETE,
  OPTIONS; headers `Authorization`, `Content-Type`, `X-Request-ID`; `X-Request-ID` exposed.
- **Authentication.** Endpoints depend on `CurrentUser`, directly or through a permission guard
  (`docs/auth.md`). A valid token says who is calling, nothing more.
- **Authorization**, at two levels. The route requires a permission
  (`require_permissions(permission="workshops:create")`, 403 `forbidden` without it): whether this
  user may do this kind of thing at all. The use case decides on which resources
  (`app/workshops/services/access.py`). A resource the caller may not see (someone else's draft)
  answers 404, like an id that does not exist, so the response does not confirm it is there. One
  it may see and not change (a published workshop of another organizer) answers 403. A holder of
  `workshops:moderate` is not bound by ownership. Lists are limited in the query itself, by a
  `scope` no query parameter can widen (`docs/database.md`). A resource addressed through its
  parent (`/workshops/{id}/enrollments/{eid}`) is checked to belong to that parent: the
  permission was verified on the parent.
- **Rate limits.** Each endpoint declares `@limiter.limit(...)`: `RATE_LIMIT_STRICT` on login,
  register and refresh, `RATE_LIMIT_DEFAULT` on the rest. It is checked when the endpoint is
  called, after its dependencies, so a request with an invalid token gets 401 and does not count.
  The decorators are the whole mechanism: there is no rate-limit middleware and no global default
  limit.
- **What is public.** Login, register, refresh, the health endpoints, and `/v1/metrics` unless
  `METRICS_TOKEN` is set (`docs/metrics.md`). Swagger UI, ReDoc and `/openapi.json` exist only
  with `DOCS_ENABLED=true`.

## Usage

- A new endpoint gets three things: a permission guard as its user dependency (see
  `Viewer`/`Organizer`/`Attendee` in `app/workshops/api/router.py`), an ownership check in its
  use case for anything addressed by id, and `@limiter.limit(settings.RATE_LIMIT_DEFAULT)` (with a
  `request: Request` parameter, which slowapi needs). `CurrentUser` alone is for routes about the
  caller itself, such as `/auth/me`.
- A new kind of resource is added to `RESOURCES` in `tests/integration/api/test_authorization.py`
  (how to create a private one), and every route that names it is then requested by a second
  user.
- A new permission is reference data: a migration inserts it and grants it to the roles
  (`migrations/versions/0008_workshops.py`).
- A public endpoint is added to `PUBLIC` in `tests/functional/test_auth_required_on_all_endpoints.py`
  with the reason; an endpoint without a limit, to `EXEMPT` in
  `tests/unit/test_every_endpoint_has_a_rate_limit.py`.
- Behind a reverse proxy that already adds the security headers, set
  `SECURITY_HEADERS_ENABLED=false`.

## Configuration

| Setting | Default | Outside local |
|---|---|---|
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Must be set: the proxy address or subnet, or empty when clients connect directly. Unset or `*` aborts startup |
| `ALLOWED_HOSTS` | `["*"]` | Explicit host names; `*` or empty aborts startup |
| `ALLOWED_ORIGINS` | localhost frontends | Must be set: the exact origins, or `[]` when no browser calls the API. Unset or `*` aborts startup |
| `SECURITY_HEADERS_ENABLED` | `true` | |
| `HSTS_ENABLED`, `HSTS_MAX_AGE` | `false`, `31536000` | Enable behind HTTPS |
| `RATE_LIMIT_ENABLED` | `true` | |
| `RATE_LIMIT_STRICT`, `RATE_LIMIT_DEFAULT` | `5/minute`, `60/minute` | |
| `DOCS_ENABLED` | `false` (`true` in `.env.example`) | Leave it off unless the API is meant to be explored |

## Guarantees and limits

- Every route answers 401 without a token, and to a token that is not valid, unless listed in
  `PUBLIC`; every endpoint has a limit unless listed in `EXEMPT`. Both are checked by tests that
  walk the whole API.
- Every route with a path parameter answers 403 or 404 to a user who does not own the resource:
  `tests/integration/api/test_authorization.py` walks them against a real database and fails for
  a route whose resource it does not know how to create.
- The rate limit key is the client address. Behind a reverse proxy that is not in
  `FORWARDED_ALLOW_IPS`, that address is the proxy's for every client and they all share one
  bucket: five failed logins a minute by anyone would lock everybody out. That is why the setting
  has to be stated outside local.
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
| `app/core/security/trusted_host.py` | `TrustedHostMiddleware` with the probe exemption |
| `app/core/ratelimit.py` | `limiter` |
| `app/core/config.py` | Settings and their validators |
