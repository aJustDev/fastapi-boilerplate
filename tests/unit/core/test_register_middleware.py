from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.exceptions.middleware import UnhandledErrorMiddleware
from app.core.logging.middleware import RequestIdMiddleware
from app.core.metrics.middleware import PrometheusMiddleware
from app.core.middleware import PROBE_PATHS
from app.core.security.headers import SecurityHeadersMiddleware
from app.core.security.trusted_host import TrustedHostMiddleware
from main import app
from tests._routes import iter_api_routes


def test_middleware_stack_order():
    # Outermost first. ProxyHeaders before everything (real client IP for the rate limit
    # and the logs), TrustedHost before any work.
    assert [m.cls for m in app.user_middleware] == [
        ProxyHeadersMiddleware,
        TrustedHostMiddleware,
        PrometheusMiddleware,
        RequestIdMiddleware,
        SecurityHeadersMiddleware,
        CORSMiddleware,
        GZipMiddleware,
        # Innermost: the 500 of an unhandled error goes back through everything above.
        UnhandledErrorMiddleware,
    ]


def test_the_limiter_is_reachable_for_the_endpoint_decorators():
    # slowapi looks it up on app.state when a decorated endpoint is called.
    assert app.state.limiter is not None


def test_the_paths_exempt_from_the_host_check_are_the_probes():
    # An exemption for a route that does not exist, or for one that returns data, would
    # be a hole: the list is exactly the health endpoints.
    health = {ctx.path for ctx in iter_api_routes() if "/health/" in ctx.path}
    assert set(PROBE_PATHS) == health
