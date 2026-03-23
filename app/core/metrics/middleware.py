import time

from starlette.routing import Match
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics.instruments import (
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
)

# Paths excluded from metrics to avoid self-referential noise.
_EXCLUDED_PREFIXES = ("/v1/metrics", "/v1/health/")


class PrometheusMiddleware:
    """ASGI middleware that records HTTP request metrics for Prometheus."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path_template = self._resolve_path_template(scope)
        status_code = "500"  # default if we never see http.response.start

        http_requests_in_progress.labels(method=method).inc()
        start = time.monotonic()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = str(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.monotonic() - start
            http_requests_in_progress.labels(method=method).dec()
            http_requests_total.labels(
                method=method, path_template=path_template, status=status_code
            ).inc()
            http_request_duration_seconds.labels(
                method=method, path_template=path_template
            ).observe(duration)

    @staticmethod
    def _resolve_path_template(scope: Scope) -> str:
        """Extract the route template (e.g. /v1/items/{item_id}) from the ASGI scope.

        Falls back to the raw path if no matching route is found.
        """
        app = scope.get("app")
        if app is None:
            return scope.get("path", "/")

        routes = getattr(app, "routes", [])
        for route in routes:
            match, _ = route.matches(scope)
            if match == Match.FULL:
                return getattr(route, "path", scope.get("path", "/"))

        return scope.get("path", "/")
