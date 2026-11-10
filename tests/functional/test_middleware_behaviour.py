"""The network settings do what they say, through the real middleware stack.

`test_register_middleware.py` checks which middlewares are registered and in what order;
these tests check what each setting lets through, so a stack with the right classes and
the wrong arguments (every host allowed, every proxy trusted) does not pass.
"""

import pytest
from fastapi import Request
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from main import create_app

API_HOST = "api.example.com"
FRONTEND = "https://app.example.com"
PROXY = "10.0.0.5"


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "ALLOWED_HOSTS", [API_HOST])
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", [FRONTEND])
    monkeypatch.setattr(settings, "FORWARDED_ALLOW_IPS", PROXY)
    application = create_app()

    @application.get("/_seen")
    async def seen(request: Request) -> dict[str, str | None]:
        return {"client": request.client.host if request.client else None}

    return application


def _client(app, peer: str = PROXY) -> AsyncClient:
    transport = ASGITransport(app=app, client=(peer, 5000))
    return AsyncClient(transport=transport, base_url=f"http://{API_HOST}")


class TestHost:
    async def test_the_configured_host_is_served(self, app):
        async with _client(app) as client:
            assert (await client.get("/_seen")).status_code == 200

    async def test_another_host_is_rejected(self, app):
        async with _client(app) as client:
            response = await client.get("/_seen", headers={"Host": "evil.example.org"})
        assert response.status_code == 400
        assert response.json()["code"] == "invalid_host"

    async def test_probes_answer_under_any_host(self, app):
        async with _client(app) as client:
            response = await client.get("/v1/health/liveness", headers={"Host": "localhost:8000"})
        assert response.status_code == 200


class TestCors:
    async def test_the_configured_origin_may_read_the_response(self, app):
        async with _client(app) as client:
            response = await client.get("/_seen", headers={"Origin": FRONTEND})
        assert response.headers["Access-Control-Allow-Origin"] == FRONTEND

    async def test_another_origin_gets_no_permission(self, app):
        async with _client(app) as client:
            simple = await client.get("/_seen", headers={"Origin": "https://evil.example.org"})
            preflight = await client.options(
                "/_seen",
                headers={
                    "Origin": "https://evil.example.org",
                    "Access-Control-Request-Method": "GET",
                },
            )
        assert "Access-Control-Allow-Origin" not in simple.headers
        assert "Access-Control-Allow-Origin" not in preflight.headers
        assert preflight.status_code == 400


class TestForwardedHeaders:
    async def test_the_listed_proxy_is_believed(self, app):
        async with _client(app, peer=PROXY) as client:
            response = await client.get("/_seen", headers={"X-Forwarded-For": "198.51.100.7"})
        assert response.json() == {"client": "198.51.100.7"}

    async def test_anyone_else_is_not(self, app):
        # Otherwise a client picks the address its rate limit and its log lines are under.
        async with _client(app, peer="203.0.113.9") as client:
            response = await client.get("/_seen", headers={"X-Forwarded-For": "198.51.100.7"})
        assert response.json() == {"client": "203.0.113.9"}
