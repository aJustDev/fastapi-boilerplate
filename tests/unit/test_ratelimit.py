from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from slowapi import Limiter

from app.core.db import get_session
from app.core.ratelimit import limiter
from main import app


class TestLimiterInstance:
    def test_limiter_is_slowapi_instance(self):
        assert isinstance(limiter, Limiter)

    def test_limiter_uses_memory_storage(self):
        assert limiter._storage_uri == "memory://"


class TestRateLimitIntegration:
    """Tests with rate limiting enabled against the real app."""

    @pytest.fixture(autouse=True)
    def _enable_limiter(self):
        limiter.enabled = True
        limiter.reset()
        yield
        limiter.enabled = False

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.flush = AsyncMock()
        session.refresh = AsyncMock()
        session.delete = AsyncMock()
        session.add = MagicMock()
        # Chain execute → scalars → first to return None (user not found → 401)
        scalars_result = MagicMock()
        scalars_result.first.return_value = None
        execute_result = MagicMock()
        execute_result.scalars.return_value = scalars_result
        session.execute = AsyncMock(return_value=execute_result)
        return session

    @pytest.fixture
    async def client(self, mock_session):
        async def _override_session() -> AsyncGenerator:
            yield mock_session

        app.dependency_overrides[get_session] = _override_session
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
        app.dependency_overrides.clear()

    async def test_rate_limit_exceeded_returns_429(self, client: AsyncClient):
        # The strict limit is 5/minute; send 6 requests
        for _ in range(5):
            await client.post(
                "/v1/auth/login",
                data={"username": "test", "password": "test"},
            )

        response = await client.post(
            "/v1/auth/login",
            data={"username": "test", "password": "test"},
        )
        assert response.status_code == 429
        assert response.json()["detail"] == "Too many requests"
        assert "retry-after" in response.headers

    async def test_under_limit_not_blocked(self, client: AsyncClient):
        # 5 requests within the limit should all return 401 (auth error, not 429)
        for _ in range(5):
            response = await client.post(
                "/v1/auth/login",
                data={"username": "test", "password": "test"},
            )
            assert response.status_code == 401

    async def test_rate_limit_disabled_allows_unlimited(self, client: AsyncClient):
        limiter.enabled = False
        for _ in range(10):
            response = await client.post(
                "/v1/auth/login",
                data={"username": "test", "password": "test"},
            )
            assert response.status_code != 429
