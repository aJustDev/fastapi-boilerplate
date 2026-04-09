from httpx import AsyncClient


class TestMetricsEndpoint:
    async def test_metrics_endpoint_returns_prometheus_format(self, client: AsyncClient):
        response = await client.get("/v1/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        # Prometheus text format contains HELP and TYPE declarations
        body = response.text
        assert "# HELP" in body
        assert "# TYPE" in body

    async def test_metrics_contain_http_metrics(self, client: AsyncClient):
        # Make a request first to generate some metrics
        await client.get("/v1/health/liveness")

        response = await client.get("/v1/metrics")
        body = response.text

        assert "http_requests_total" in body
        assert "http_request_duration_seconds" in body

    async def test_metrics_contain_db_pool_gauges(self, client: AsyncClient):
        response = await client.get("/v1/metrics")
        body = response.text

        assert "db_pool_size" in body
        assert "db_pool_checked_out" in body
        assert "db_pool_checked_in" in body
        assert "db_pool_overflow" in body

    async def test_metrics_endpoint_not_tracked_in_metrics(self, client: AsyncClient):
        # Hit metrics twice — the endpoint itself should not appear in metrics
        await client.get("/v1/metrics")
        response = await client.get("/v1/metrics")
        body = response.text

        # Filter lines that are actual metric samples (not HELP/TYPE comments)
        sample_lines = [
            line for line in body.splitlines() if not line.startswith("#") and "/v1/metrics" in line
        ]
        assert sample_lines == [], f"Metrics endpoint should not track itself: {sample_lines}"
