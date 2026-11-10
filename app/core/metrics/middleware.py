import time

from fastapi.routing import APIRoute, iter_route_contexts
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.metrics.instruments import (
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
)

# Paths excluded from metrics to avoid self-referential noise.
_EXCLUDED_PREFIXES = ("/v1/metrics", "/v1/health/")

# OPTIONS (CORS preflights) and HEAD are not API work: they still count in
# http_requests_total but do not observe latency.
_METHODS_WITHOUT_DURATION = frozenset({"OPTIONS", "HEAD"})

# Single label for requests that match no route. Never the raw path: every URL a
# scanner makes up would become its own series and cardinality would be unbounded.
UNMATCHED_PATH = "__unmatched__"


class PrometheusMiddleware:
    """ASGI middleware that records HTTP request metrics for Prometheus."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # {id(route) -> full path}. Built on the first request, once every route is
        # registered, and never changes. Keyed by id because APIRoute is not hashable;
        # safe because the app owns both the routes and this middleware.
        self._templates: dict[int, str] | None = None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path.startswith(prefix) for prefix in _EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
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
            # After the call, not before: the router stores the matched route in the scope.
            path_template = self._path_template(scope)
            http_requests_in_progress.labels(method=method).dec()
            http_requests_total.labels(
                method=method, path_template=path_template, status=status_code
            ).inc()
            if method not in _METHODS_WITHOUT_DURATION:
                http_request_duration_seconds.labels(
                    method=method, path_template=path_template
                ).observe(duration)

    def _path_template(self, scope: Scope) -> str:
        """Full template (e.g. /v1/items/{item_id}) of the route that served the request.

        FastAPI's router sets `scope["route"]` when a path matches (also on a 405 for a
        wrong method); no route means the path matched nothing (404). Since FastAPI 0.140
        included routers are not flattened: `route.path` is the path declared in the child
        router, without the prefixes, so the full one comes from the route contexts.
        """
        route = scope.get("route")
        if not isinstance(route, APIRoute):
            return UNMATCHED_PATH
        if self._templates is None:
            self._templates = {
                id(ctx.route): ctx.path
                for ctx in iter_route_contexts(getattr(scope.get("app"), "routes", []))
                if isinstance(ctx.route, APIRoute) and ctx.path
            }
        return self._templates.get(id(route)) or route.path
