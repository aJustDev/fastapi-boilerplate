"""Every API endpoint declares a rate limit, unless it is listed as exempt.

The limit is a decorator (`@limiter.limit(...)`) per endpoint; a new endpoint without it
would accept unlimited requests and nothing else would notice.
"""

import pytest

from app.core.ratelimit import limiter
from tests._routes import iter_api_routes

# Path -> reason. Probes and scrapes must never be throttled.
EXEMPT: dict[str, str] = {
    "/v1/health/liveness": "orchestrator probe",
    "/v1/health/readiness": "orchestrator probe",
    "/v1/metrics": "Prometheus scrape",
}


def _routes() -> list[tuple[str, str]]:
    return sorted(
        (ctx.path, f"{ctx.route.endpoint.__module__}.{ctx.route.endpoint.__name__}")
        for ctx in iter_api_routes()
        if ctx.path not in EXEMPT
    )


def test_scanner_sees_the_api():
    assert len(_routes()) >= 10


@pytest.mark.parametrize(("path", "endpoint"), _routes())
def test_endpoint_has_a_rate_limit(path: str, endpoint: str):
    # slowapi keys its per-route limits by "<module>.<function>".
    assert limiter._route_limits.get(endpoint), (
        f"{path} ({endpoint}) has no @limiter.limit(...): add RATE_LIMIT_DEFAULT "
        "(or RATE_LIMIT_STRICT for unauthenticated endpoints), or list it in EXEMPT."
    )
