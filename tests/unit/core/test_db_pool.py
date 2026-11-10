from unittest.mock import patch

import pytest

from app.core.config import Settings
from app.core.db import build_asyncpg_dsn


class TestPoolSettings:
    def test_default_pool_values(self):
        s = Settings(DATABASE_URL="postgresql+asyncpg://u:p@localhost/db")
        assert s.DB_POOL_SIZE == 5
        assert s.DB_MAX_OVERFLOW == 10
        assert s.DB_POOL_TIMEOUT == 30

    def test_pool_values_from_env(self):
        with patch.dict(
            "os.environ",
            {
                "DB_POOL_SIZE": "20",
                "DB_MAX_OVERFLOW": "15",
                "DB_POOL_TIMEOUT": "60",
            },
        ):
            s = Settings(DATABASE_URL="postgresql+asyncpg://u:p@localhost/db")
            assert s.DB_POOL_SIZE == 20
            assert s.DB_MAX_OVERFLOW == 15
            assert s.DB_POOL_TIMEOUT == 60


class TestAsyncpgDsn:
    def test_listener_dsn_follows_database_url(self):
        # Set directly (pgbouncer, managed provider), DATABASE_URL must win over the
        # DB_* defaults, or LISTEN would connect to a different database than the pool.
        with patch(
            "app.core.db.settings.DATABASE_URL",
            "postgresql+asyncpg://user:secret@pgbouncer:6432/prod",
        ):
            assert build_asyncpg_dsn() == "postgresql://user:secret@pgbouncer:6432/prod"


class TestJobLeaseSetting:
    def test_lease_shorter_than_twice_the_handler_timeout_is_rejected(self):
        with pytest.raises(ValueError, match="JOB_LEASE_SECONDS"):
            Settings(JOB_LEASE_SECONDS=100, JOB_HANDLER_TIMEOUT_SECONDS=60)


class TestConnectTimeout:
    def test_engine_connections_use_the_configured_connect_timeout(self):
        # asyncpg waits 60 s by default; an unreachable host that drops packets would
        # make every connection attempt wait that long.
        from app.core.db import ENGINE_OPTIONS

        assert ENGINE_OPTIONS["connect_args"]["timeout"] == Settings().DB_CONNECT_TIMEOUT
