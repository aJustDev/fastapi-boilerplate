from unittest.mock import AsyncMock, MagicMock

from app.core.metrics.middleware import PrometheusMiddleware


class TestPrometheusMiddleware:
    async def test_records_request_count(self):
        from app.core.metrics.instruments import http_requests_total

        before = http_requests_total.labels(
            method="GET", path_template="/v1/items", status="200"
        )._value.get()

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        mw = PrometheusMiddleware(inner_app)
        scope = {"type": "http", "method": "GET", "path": "/v1/items"}
        await mw(scope, AsyncMock(), AsyncMock())

        after = http_requests_total.labels(
            method="GET", path_template="/v1/items", status="200"
        )._value.get()
        assert after == before + 1.0

    async def test_records_request_duration(self):
        from app.core.metrics.instruments import http_request_duration_seconds

        before = http_request_duration_seconds.labels(
            method="POST", path_template="/v1/items"
        )._sum.get()

        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = PrometheusMiddleware(inner_app)
        scope = {"type": "http", "method": "POST", "path": "/v1/items"}
        await mw(scope, AsyncMock(), AsyncMock())

        after = http_request_duration_seconds.labels(
            method="POST", path_template="/v1/items"
        )._sum.get()
        assert after > before

    async def test_excludes_metrics_path(self):
        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = PrometheusMiddleware(inner_app)
        scope = {"type": "http", "method": "GET", "path": "/v1/metrics"}
        await mw(scope, AsyncMock(), AsyncMock())

        from app.core.metrics.instruments import http_requests_total

        # No metrics recorded for the excluded path
        samples = list(http_requests_total.collect()[0].samples)
        metric_paths = [s.labels.get("path_template") for s in samples]
        assert "/v1/metrics" not in metric_paths

    async def test_excludes_health_paths(self):
        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = PrometheusMiddleware(inner_app)
        scope = {"type": "http", "method": "GET", "path": "/v1/health/liveness"}
        await mw(scope, AsyncMock(), AsyncMock())

        from app.core.metrics.instruments import http_requests_total

        samples = list(http_requests_total.collect()[0].samples)
        metric_paths = [s.labels.get("path_template") for s in samples]
        assert "/v1/health/liveness" not in metric_paths

    async def test_skips_non_http_scopes(self):
        inner = AsyncMock()
        mw = PrometheusMiddleware(inner)
        await mw({"type": "websocket"}, AsyncMock(), AsyncMock())
        inner.assert_called_once()

    async def test_resolves_path_template_from_route(self):
        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        # Mock a route that matches
        from starlette.routing import Match

        mock_route = MagicMock()
        mock_route.matches.return_value = (Match.FULL, {})
        mock_route.path = "/v1/items/{item_id}"

        mock_app = MagicMock()
        mock_app.routes = [mock_route]

        mw = PrometheusMiddleware(inner_app)
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/v1/items/42",
            "app": mock_app,
        }
        await mw(scope, AsyncMock(), AsyncMock())

        from app.core.metrics.instruments import http_requests_total

        samples = list(http_requests_total.collect()[0].samples)
        metric_paths = [s.labels.get("path_template") for s in samples]
        assert "/v1/items/{item_id}" in metric_paths
        assert "/v1/items/42" not in metric_paths
