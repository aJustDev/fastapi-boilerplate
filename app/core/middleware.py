from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.logging.middleware import RequestIdMiddleware
from app.core.metrics.middleware import PrometheusMiddleware
from app.core.ratelimit import limiter
from app.core.security.headers import SecurityHeadersMiddleware


def register_middleware(app: FastAPI) -> None:
    # Execution order is bottom-to-top (last added = outermost, runs first on request).
    #
    # Request:  ProxyHeaders -> TrustedHost -> Prometheus -> RequestId -> SlowAPI
    #           -> SecurityHeaders -> CORS -> GZip -> App
    #
    # ProxyHeaders goes first so every later layer (rate limit keys, logs) sees the real
    # client address; TrustedHost rejects a forged Host before any work is done.

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        # Without it the browser hides the header from JavaScript.
        expose_headers=["X-Request-ID"],
    )
    if settings.SECURITY_HEADERS_ENABLED:
        app.add_middleware(
            SecurityHeadersMiddleware,
            hsts=settings.HSTS_ENABLED,
            hsts_max_age=settings.HSTS_MAX_AGE,
            csp_exempt_paths=[
                p
                for p in (
                    app.docs_url,
                    app.redoc_url,
                    app.openapi_url,
                    app.swagger_ui_oauth2_redirect_url,
                )
                if p
            ],
        )

    # Registered even with RATE_LIMIT_ENABLED=false: `limiter.enabled` already skips the
    # checks, and the stack under test stays the one that is deployed.
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(RequestIdMiddleware)

    if settings.METRICS_ENABLED:
        app.add_middleware(PrometheusMiddleware)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.FORWARDED_ALLOW_IPS)
