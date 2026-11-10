from unittest.mock import AsyncMock

from fastapi.routing import APIRoute

from app.core.metrics.middleware import UNMATCHED_PATH, PrometheusMiddleware


async def _endpoint() -> None:
    return None


def _routed_app(path: str):
    """Inner ASGI app that behaves like the router: stores the matched route in the scope."""

    async def inner_app(scope, receive, send):
        scope["route"] = APIRoute(path, _endpoint)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    return inner_app


class TestPrometheusMiddleware:
    async def test_records_request_count(self):
        from app.core.metrics.instruments import http_requests_total

        before = http_requests_total.labels(
            method="GET", path_template="/v1/things", status="200"
        )._value.get()

        mw = PrometheusMiddleware(_routed_app("/v1/things"))
        scope = {"type": "http", "method": "GET", "path": "/v1/things"}
        await mw(scope, AsyncMock(), AsyncMock())

        after = http_requests_total.labels(
            method="GET", path_template="/v1/things", status="200"
        )._value.get()
        assert after == before + 1.0

    async def test_records_request_duration(self):
        from app.core.metrics.instruments import http_request_duration_seconds

        before = http_request_duration_seconds.labels(
            method="POST", path_template="/v1/things"
        )._sum.get()

        mw = PrometheusMiddleware(_routed_app("/v1/things"))
        scope = {"type": "http", "method": "POST", "path": "/v1/things"}
        await mw(scope, AsyncMock(), AsyncMock())

        after = http_request_duration_seconds.labels(
            method="POST", path_template="/v1/things"
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
        mw = PrometheusMiddleware(_routed_app("/v1/things/{thing_id}"))
        scope = {"type": "http", "method": "GET", "path": "/v1/things/42"}
        await mw(scope, AsyncMock(), AsyncMock())

        from app.core.metrics.instruments import http_requests_total

        samples = list(http_requests_total.collect()[0].samples)
        metric_paths = [s.labels.get("path_template") for s in samples]
        assert "/v1/things/{thing_id}" in metric_paths
        assert "/v1/things/42" not in metric_paths

    async def test_unmatched_request_never_labels_raw_path(self):
        # A scanner probing made-up URLs must not create one series per URL.
        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = PrometheusMiddleware(inner_app)
        scope = {"type": "http", "method": "GET", "path": "/wp-admin/setup.php"}
        await mw(scope, AsyncMock(), AsyncMock())

        from app.core.metrics.instruments import http_requests_total

        samples = list(http_requests_total.collect()[0].samples)
        metric_paths = [s.labels.get("path_template") for s in samples]
        assert UNMATCHED_PATH in metric_paths
        assert "/wp-admin/setup.php" not in metric_paths

    async def test_options_counts_but_does_not_observe_duration(self):
        from app.core.metrics.instruments import (
            http_request_duration_seconds,
            http_requests_total,
        )

        labels = {"method": "OPTIONS", "path_template": "/v1/things"}
        count_before = http_requests_total.labels(**labels, status="200")._value.get()
        sum_before = http_request_duration_seconds.labels(**labels)._sum.get()

        mw = PrometheusMiddleware(_routed_app("/v1/things"))
        await mw(
            {"type": "http", "method": "OPTIONS", "path": "/v1/things"}, AsyncMock(), AsyncMock()
        )

        assert http_requests_total.labels(**labels, status="200")._value.get() == count_before + 1
        assert http_request_duration_seconds.labels(**labels)._sum.get() == sum_before
