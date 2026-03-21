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


class TestLogSystemInfo:
    @patch("app.core.startup.settings")
    def test_logs_expected_content(self, mock_settings, caplog):
        mock_settings.APP_NAME = "TestApp"
        mock_settings.APP_VERSION = "1.0.0"
        mock_settings.ENVIRONMENT = "production"
        mock_settings.LOG_LEVEL = "debug"
        mock_settings.DATABASE_URL = "postgresql+asyncpg://user:pass@db-host:5432/mydb"

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            log_system_info("OK")

        log_text = caplog.text
        assert "SYSTEM CONFIGURATION" in log_text
        assert "TestApp" in log_text
        assert "1.0.0" in log_text
        assert "Production" in log_text
        assert "DEBUG" in log_text
        assert "db-host:5432" in log_text
        assert "OK" in log_text

    @patch("app.core.startup.settings")
    def test_logs_unavailable_status(self, mock_settings, caplog):
        mock_settings.APP_NAME = "App"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "local"
        mock_settings.LOG_LEVEL = "info"
        mock_settings.DATABASE_URL = "postgresql+asyncpg://u:p@localhost:5432/db"

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            log_system_info("UNAVAILABLE")

        assert "UNAVAILABLE" in caplog.text

    @patch("app.core.startup.settings")
    def test_handles_url_without_at_sign(self, mock_settings, caplog):
        mock_settings.APP_NAME = "App"
        mock_settings.APP_VERSION = "0.1.0"
        mock_settings.ENVIRONMENT = "local"
        mock_settings.LOG_LEVEL = "info"
        mock_settings.DATABASE_URL = "sqlite:///test.db"

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            log_system_info("OK")

        assert "unknown" in caplog.text
