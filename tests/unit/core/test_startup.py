import logging
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.startup import check_database, log_system_info


class TestCheckDatabase:
    async def test_returns_ok_when_connection_succeeds(self):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()

        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_conn
        mock_cm.__aexit__.return_value = False

        mock_engine = MagicMock()
        mock_engine.connect.return_value = mock_cm

        result = await check_database(mock_engine)

        assert result == "OK"

    async def test_returns_unavailable_when_connection_fails(self):
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = Exception("Connection refused")

        result = await check_database(mock_engine)

        assert result == "UNAVAILABLE"


def _mock_engine_with_advisory_lock(*, acquired: bool = True) -> MagicMock:
    """Create a mock engine that returns a result for pg_try_advisory_lock."""
    mock_result = MagicMock()
    mock_result.scalar.return_value = acquired

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock(return_value=mock_result)

    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_cm.__aexit__ = AsyncMock(return_value=False)

    engine = MagicMock()
    engine.connect.return_value = mock_cm
    return engine


class TestLogSystemInfo:
    @patch("app.core.startup.settings")
    async def test_banner_leader_logs_full_config(self, mock_settings, caplog):
        mock_settings.APP_NAME = "TestApp"
        mock_settings.APP_VERSION = "1.0.0"
        mock_settings.ENVIRONMENT = "production"
        mock_settings.LOG_LEVEL = "debug"
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@db-host:5432/mydb"
        mock_settings.DB_POOL_SIZE = 5
        mock_settings.DB_MAX_OVERFLOW = 10
        mock_settings.DB_POOL_TIMEOUT = 30

        engine = _mock_engine_with_advisory_lock(acquired=True)

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            await log_system_info(engine, "OK")

        log_text = caplog.text
        assert "SYSTEM CONFIGURATION" in log_text
        assert "TestApp" in log_text
        assert "1.0.0" in log_text
        assert "Production" in log_text
        assert "DEBUG" in log_text
        assert "db-host:5432" in log_text
        assert "OK" in log_text
        assert "Pool" in log_text
        assert "5+10" in log_text
        assert "timeout 30s" in log_text

    @patch("app.core.startup.settings")
    async def test_non_leader_logs_short_line(self, mock_settings, caplog):
        mock_settings.APP_NAME = "App"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "local"
        mock_settings.LOG_LEVEL = "info"
        mock_settings.DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"
        mock_settings.DB_POOL_SIZE = 5
        mock_settings.DB_MAX_OVERFLOW = 10
        mock_settings.DB_POOL_TIMEOUT = 30

        engine = _mock_engine_with_advisory_lock(acquired=False)

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            await log_system_info(engine, "OK")

        assert "Worker ready" in caplog.text
        assert "SYSTEM CONFIGURATION" not in caplog.text

    @patch("app.core.startup.settings")
    async def test_logs_unavailable_status(self, mock_settings, caplog):
        mock_settings.APP_NAME = "App"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "local"
        mock_settings.LOG_LEVEL = "info"
        mock_settings.DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"
        mock_settings.DB_POOL_SIZE = 5
        mock_settings.DB_MAX_OVERFLOW = 10
        mock_settings.DB_POOL_TIMEOUT = 30

        engine = _mock_engine_with_advisory_lock(acquired=True)

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            await log_system_info(engine, "UNAVAILABLE")

        assert "UNAVAILABLE" in caplog.text

    @patch("app.core.startup.settings")
    async def test_handles_url_without_at_sign(self, mock_settings, caplog):
        mock_settings.APP_NAME = "App"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "local"
        mock_settings.LOG_LEVEL = "info"
        mock_settings.DATABASE_URL = "sqlite:///test.db"
        mock_settings.DB_POOL_SIZE = 5
        mock_settings.DB_MAX_OVERFLOW = 10
        mock_settings.DB_POOL_TIMEOUT = 30

        engine = _mock_engine_with_advisory_lock(acquired=True)

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            await log_system_info(engine, "OK")

        assert "unknown" in caplog.text
