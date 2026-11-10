"""What is reachable without credentials can be closed: API docs and metrics."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from main import create_app


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_api_docs_are_not_served_when_disabled(monkeypatch, path: str):
    monkeypatch.setattr(settings, "DOCS_ENABLED", False)
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 404


async def test_api_docs_are_served_when_enabled(client: AsyncClient):
    assert (await client.get("/docs")).status_code == 200
    assert (await client.get("/openapi.json")).status_code == 200


class TestMetricsToken:
    async def test_open_without_a_token_configured(self, client: AsyncClient):
        assert (await client.get("/v1/metrics")).status_code == 200

    async def test_with_a_token_the_scrape_must_present_it(self, client: AsyncClient, monkeypatch):
        monkeypatch.setattr(settings, "METRICS_TOKEN", "scrape-secret")

        anonymous = await client.get("/v1/metrics")
        wrong = await client.get("/v1/metrics", headers={"Authorization": "Bearer nope"})
        right = await client.get("/v1/metrics", headers={"Authorization": "Bearer scrape-secret"})

        assert anonymous.status_code == wrong.status_code == 401
        assert anonymous.json()["code"] == "unauthenticated"
        assert right.status_code == 200
        assert "http_requests_total" in right.text
