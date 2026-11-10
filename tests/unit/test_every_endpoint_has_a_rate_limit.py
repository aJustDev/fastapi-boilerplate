"""Every API endpoint is rate limited at the tier that fits it, unless listed as exempt.

The limit is a decorator (`@limiter.limit(...)`) per endpoint; a new endpoint without it
would accept unlimited requests and nothing else would notice. Declaring it is not enough
either: placed above `@router...`, the route keeps the undecorated function and slowapi
never runs, while the limit still looks registered.
"""

import pytest
from limits import parse

from app.core.config import settings
from app.core.ratelimit import limiter
from tests._routes import iter_api_routes

# (method, path) -> reason. Probes and scrapes must never be throttled.
EXEMPT: dict[tuple[str, str], str] = {
    ("GET", "/v1/health/liveness"): "orchestrator probe",
    ("GET", "/v1/health/readiness"): "orchestrator probe",
    ("GET", "/v1/metrics"): "Prometheus scrape",
}

# (method, path) of the routes limited at RATE_LIMIT_STRICT: the ones anybody can call
# and that cost a password hash or hand out tokens. Everything else is RATE_LIMIT_DEFAULT.
STRICT = {
    ("POST", "/v1/auth/login"),
    ("POST", "/v1/auth/register"),
    ("POST", "/v1/auth/refresh"),
}


def _routes() -> list[tuple[str, str, object]]:
    found = []
    for ctx in iter_api_routes():
        for method in sorted(ctx.route.methods - {"HEAD", "OPTIONS"}):
            if (method, ctx.path) not in EXEMPT:
                found.append((method, ctx.path, ctx.route.endpoint))
    return sorted(found, key=lambda route: (route[1], route[0]))


ROUTES = _routes()
IDS = [f"{method} {path}" for method, path, _ in ROUTES]


def _key(endpoint: object) -> str:
    # slowapi keys its per-route limits by "<module>.<function>".
    return f"{endpoint.__module__}.{endpoint.__name__}"  # type: ignore[attr-defined]


def test_scanner_sees_the_api():
    assert len(ROUTES) >= 10


def test_lists_have_no_stale_entries():
    live = {(m, ctx.path) for ctx in iter_api_routes() for m in ctx.route.methods}
    assert not set(EXEMPT) - live, f"EXEMPT lists routes that do not exist: {set(EXEMPT) - live}"
    assert not STRICT - live, f"STRICT lists routes that do not exist: {STRICT - live}"


@pytest.mark.parametrize(("method", "path", "endpoint"), ROUTES, ids=IDS)
def test_endpoint_has_a_rate_limit(method: str, path: str, endpoint: object):
    assert limiter._route_limits.get(_key(endpoint)), (
        f"{method} {path} has no @limiter.limit(...): add RATE_LIMIT_DEFAULT (or "
        "RATE_LIMIT_STRICT for unauthenticated endpoints), or list it in EXEMPT."
    )


@pytest.mark.parametrize(("method", "path", "endpoint"), ROUTES, ids=IDS)
def test_the_route_runs_the_limited_function(method: str, path: str, endpoint: object):
    # slowapi returns a wrapper; the route must hold it. With `@limiter.limit` above
    # `@router...`, the route holds the bare function and no request is ever counted.
    assert hasattr(endpoint, "__wrapped__"), (
        f"{method} {path}: put @limiter.limit(...) under the @router decorator, not above it."
    )


@pytest.mark.parametrize(("method", "path", "endpoint"), ROUTES, ids=IDS)
def test_endpoint_is_limited_at_its_tier(method: str, path: str, endpoint: object):
    expected = (
        settings.RATE_LIMIT_STRICT if (method, path) in STRICT else settings.RATE_LIMIT_DEFAULT
    )
    declared = [limit.limit for limit in limiter._route_limits[_key(endpoint)]]
    assert declared == [parse(expected)], f"{method} {path} is limited at {declared}"
