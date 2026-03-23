from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.logging.middleware import RequestIdMiddleware
from app.core.metrics.middleware import PrometheusMiddleware
from app.core.ratelimit import limiter


def register_middleware(app: FastAPI) -> None:
    # Middleware execution order is bottom-to-top (last added = outermost).
    # Outermost runs first on request and last on response.
    #
    # Request flow:  Prometheus → RequestId → SlowAPI → CORS → GZip → App
    # Response flow:  App → GZip → CORS → SlowAPI → RequestId → Prometheus

    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.RATE_LIMIT_ENABLED:
        app.state.limiter = limiter
        app.add_middleware(SlowAPIMiddleware)

    app.add_middleware(RequestIdMiddleware)

    if settings.METRICS_ENABLED:
        app.add_middleware(PrometheusMiddleware)
