from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from main import app


class TestHealthEndpoints:
    async def test_liveness_returns_alive(self):
        mock_session = AsyncMock()

        async def _override():
            yield mock_session

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/v1/health/liveness")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"status": "alive"}

    async def test_readiness_when_ready(self):
        mock_session = AsyncMock()

        async def _override():
            yield mock_session

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            app.state.ready = True
            mock_conn = AsyncMock()
            mock_connect = AsyncMock()
            mock_connect.__aenter__ = AsyncMock(return_value=mock_conn)
            mock_connect.__aexit__ = AsyncMock(return_value=False)
            with patch("app.api.v1.health.engine") as mock_engine:
                mock_engine.connect.return_value = mock_connect
                response = await client.get("/v1/health/readiness")
        app.dependency_overrides.clear()

        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    async def test_readiness_when_not_ready(self):
        mock_session = AsyncMock()

        async def _override():
            yield mock_session

        app.dependency_overrides[get_session] = _override
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            app.state.ready = False
            response = await client.get("/v1/health/readiness")
        app.dependency_overrides.clear()

        assert response.status_code == 503
        assert response.json() == {"status": "not ready"}
