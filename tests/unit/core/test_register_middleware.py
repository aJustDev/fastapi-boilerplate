from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.exceptions.middleware import UnhandledErrorMiddleware
from app.core.logging.middleware import RequestIdMiddleware
from app.core.metrics.middleware import PrometheusMiddleware
from app.core.security.headers import SecurityHeadersMiddleware
from main import app


def test_middleware_stack_order():
    # Outermost first. ProxyHeaders before everything (real client IP for the rate limit
    # and the logs), TrustedHost before any work, and the rate limiter registered even
    # though the test suite disables the limiter: the stack under test is the deployed one.
    assert [m.cls for m in app.user_middleware] == [
        ProxyHeadersMiddleware,
        TrustedHostMiddleware,
        PrometheusMiddleware,
        RequestIdMiddleware,
        SlowAPIMiddleware,
        SecurityHeadersMiddleware,
        CORSMiddleware,
        GZipMiddleware,
        # Innermost: the 500 of an unhandled error goes back through everything above.
        UnhandledErrorMiddleware,
    ]
