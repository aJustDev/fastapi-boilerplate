from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.core.db import (
    _set_local_timeouts,
    build_asyncpg_dsn,
    engine_options,
    set_timeouts_per_transaction,
)


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


class TestBehindATransactionPooler:
    """Nothing may live on the connection between transactions."""

    def test_direct_connections_keep_the_caches_and_send_the_timeouts(self):
        connect_args = engine_options(transaction_pooler=False)["connect_args"]

        assert "statement_cache_size" not in connect_args
        assert set(connect_args["server_settings"]) == {"statement_timeout", "lock_timeout"}

    def test_behind_a_pooler_no_statement_is_cached_and_each_has_its_own_name(self):
        connect_args = engine_options(transaction_pooler=True)["connect_args"]

        assert connect_args["statement_cache_size"] == 0
        assert connect_args["prepared_statement_cache_size"] == 0
        name = connect_args["prepared_statement_name_func"]
        assert name() != name()
        # PgBouncer refuses a connection that sends parameters it does not know.
        assert "server_settings" not in connect_args

    def test_behind_a_pooler_the_timeouts_are_set_in_each_transaction(self):
        engine = create_async_engine("postgresql+asyncpg://u:p@localhost/db")

        set_timeouts_per_transaction(engine)

        assert event.contains(engine.sync_engine, "begin", _set_local_timeouts)

    def test_a_direct_url_with_sslmode_is_refused_like_database_url(self):
        with pytest.raises(ValueError, match="DB_DIRECT_URL"):
            Settings(DB_DIRECT_URL="postgresql+asyncpg://u:p@db/app?sslmode=require")

    def test_the_direct_url_falls_back_to_database_url(self):
        url = "postgresql+asyncpg://u:p@pooler:6543/app"
        assert Settings(DATABASE_URL=url).direct_database_url == url
        direct = "postgresql+asyncpg://u:p@db:5432/app"
        assert Settings(DATABASE_URL=url, DB_DIRECT_URL=direct).direct_database_url == direct
