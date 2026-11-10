import asyncio
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


class TestReadinessFollowsTheDatabase:
    """Readiness is asked on every probe, so an instance recovers without a restart."""

    @staticmethod
    def _engine(*, fails: bool, hangs: bool = False) -> MagicMock:
        async def execute(*_):
            if hangs:
                await asyncio.sleep(60)

        conn = AsyncMock()
        conn.execute = execute
        connection = MagicMock()
        connection.__aenter__ = AsyncMock(
            return_value=conn, side_effect=ConnectionRefusedError if fails else None
        )
        connection.__aexit__ = AsyncMock(return_value=False)
        engine = MagicMock()
        engine.connect.return_value = connection
        return engine

    async def test_database_down_then_up(self):
        app.state.ready = True
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with patch("app.api.v1.health.engine", self._engine(fails=True)):
                down = await client.get("/v1/health/readiness")
            with patch("app.api.v1.health.engine", self._engine(fails=False)):
                up = await client.get("/v1/health/readiness")

        assert (down.status_code, down.json()) == (503, {"status": "database unavailable"})
        assert (up.status_code, up.json()) == (200, {"status": "ready"})

    async def test_a_database_that_does_not_answer_is_not_waited_for(self):
        app.state.ready = True
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            with (
                patch("app.api.v1.health.engine", self._engine(fails=False, hangs=True)),
                patch("app.api.v1.health.READINESS_DB_CHECK_SECONDS", 0.05),
            ):
                response = await client.get("/v1/health/readiness")

        assert response.status_code == 503
