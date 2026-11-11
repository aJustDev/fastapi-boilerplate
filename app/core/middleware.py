from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.core.config import settings
from app.core.exceptions.middleware import UnhandledErrorMiddleware
from app.core.logging.middleware import (
    LIVENESS_PATH,
    READINESS_PATH,
    AccessLogMiddleware,
    RequestIdMiddleware,
)
from app.core.metrics.middleware import PrometheusMiddleware
from app.core.ratelimit import limiter
from app.core.security.headers import SecurityHeadersMiddleware
from app.core.security.trusted_host import TrustedHostMiddleware

# Served whatever the Host header says (see TrustedHostMiddleware).
PROBE_PATHS = (LIVENESS_PATH, READINESS_PATH)


def register_middleware(app: FastAPI) -> None:
    # Execution order is bottom-to-top (last added = outermost, runs first on request).
    #
    # Request:  ProxyHeaders -> RequestId -> AccessLog -> TrustedHost -> Prometheus
    #           -> SecurityHeaders -> CORS -> GZip -> UnhandledError -> App
    #
    # ProxyHeaders goes first so every later layer (rate limit keys, logs) sees the real
    # client address. RequestId and AccessLog come next, so every response, a rejected
    # Host included, carries an id and leaves an access line. TrustedHost rejects a forged
    # Host before any work is done.
    # UnhandledError goes last, right around the routes, so the 500 it builds returns
    # through every other layer like any response.

    app.add_middleware(UnhandledErrorMiddleware)
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

    # The limits are the `@limiter.limit` decorators of each endpoint; slowapi finds the
    # limiter here. There is no rate-limit middleware: slowapi's only applies global
    # default limits, and it cannot see the routes of an included router.
    app.state.limiter = limiter

    if settings.METRICS_ENABLED:
        app.add_middleware(PrometheusMiddleware)

    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS, exempt_paths=PROBE_PATHS
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RequestIdMiddleware)
    # The only place forwarded headers are honored: run uvicorn with --no-proxy-headers
    # (the image does), or its own copy of this middleware reads FORWARDED_ALLOW_IPS from
    # the process environment and the two can disagree.
    app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=settings.FORWARDED_ALLOW_IPS)
