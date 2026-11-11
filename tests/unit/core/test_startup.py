import json
import logging
import re
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import startup
from app.core.logging.config import JSONFormatter
from app.core.startup import check_database, check_utc_timezone, expected_schema, log_system_info


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

    async def test_a_timeout_says_why(self, caplog):
        # A TimeoutError has no message: the warning would end in "TimeoutError: ".
        mock_engine = MagicMock()
        mock_engine.connect.side_effect = TimeoutError()

        with caplog.at_level(logging.WARNING, logger="app.core.startup"):
            await check_database(mock_engine)

        assert "TimeoutError: no answer in 3s" in caplog.text


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


CAPACITY = {"max": 100, "reserved": 3, "in_use": 12}


@pytest.fixture
def banner(monkeypatch):
    """Settings of a known deployment; the schema read and the log format are set per test."""
    for name, value in {
        "APP_NAME": "TestApp",
        "APP_VERSION": "1.0.0",
        "ENVIRONMENT": "production",
        "LOG_LEVEL": "debug",
        "DATABASE_URL": "postgresql+asyncpg://user:secret@db-host:5432/mydb",
        "DB_POOL_SIZE": 5,
        "DB_MAX_OVERFLOW": 10,
        "DB_POOL_TIMEOUT": 30,
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_DEFAULT": "60/minute",
        "RATE_LIMIT_STRICT": "5/minute",
        "DOCS_ENABLED": False,
        "METRICS_ENABLED": True,
        "METRICS_TOKEN": "",
    }.items():
        monkeypatch.setattr(f"app.core.startup.settings.{name}", value)
    monkeypatch.setattr(startup, "expected_schema", lambda: ["0009"])
    monkeypatch.setattr(startup, "json_enabled", lambda: False)
    monkeypatch.setattr(startup, "ansi_enabled", lambda: False)
    monkeypatch.setattr("app.core.startup.settings.DB_TRANSACTION_POOLER", False)
    monkeypatch.setattr(startup, "database_capacity", AsyncMock(return_value=CAPACITY))
    schema = AsyncMock(return_value=["0009"])
    monkeypatch.setattr(startup, "database_schema", schema)
    return schema


async def _log(caplog, db_status="OK", *, acquired=True, **kwargs) -> logging.LogRecord | None:
    engine = _mock_engine_with_advisory_lock(acquired=acquired)
    with caplog.at_level(logging.INFO, logger="app.core.startup"):
        await log_system_info(engine, db_status, **kwargs)
    return next((r for r in caplog.records if hasattr(r, "fields")), None)


V = "\u2502"  # the vertical line of the table
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _table(record: logging.LogRecord | None) -> list[str]:
    """The lines of the table: top border, title, separator, one per piece, bottom."""
    assert record is not None
    first, *table = record.getMessage().splitlines()
    assert first == "Startup summary"
    return table


def _rows(record: logging.LogRecord | None) -> list[tuple[str, ...]]:
    """(state, label, value) of each row, without padding or color."""
    return [
        tuple(cell.strip() for cell in ANSI.sub("", line).strip().strip(V).split(V))
        for line in _table(record)[3:-1]
    ]


class TestLogSystemInfo:
    async def test_the_leader_logs_one_table(self, banner, caplog):
        record = await _log(
            caplog, outbox_status="started", jobs_status="started", registered_jobs=5
        )

        assert _rows(record) == [
            ("ok", "Database", "db-host:5432/mydb, pool 5 + 10 overflow, timeout 30s"),
            ("ok", "Capacity", "up to 16 from this instance, 12 of 100 in use"),
            ("ok", "Outbox", "listening for events"),
            ("ok", "Jobs", "5 handlers"),
            ("on", "Limits", "60/minute, strict 5/minute, in memory per process"),
            ("off", "Docs", ""),
            ("on", "Metrics", "/v1/metrics, no token"),
        ]
        assert "secret" not in caplog.text
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    async def test_the_frame_closes_and_the_title_heads_it(self, banner, caplog, monkeypatch):
        monkeypatch.setattr(startup.socket, "gethostname", lambda: "api-1")
        monkeypatch.setattr(startup.os, "getpid", lambda: 42)

        table = _table(await _log(caplog))

        assert len({len(line) for line in table}) == 1, "every line of the frame is as wide"
        assert table[0].startswith("  \u250c") and table[-1].startswith("  \u2514")
        # The name on the left, where the process runs on the right.
        title = table[1].strip().strip(V)
        assert title.startswith(" TestApp v1.0.0   ")
        assert title.endswith("   production | log DEBUG | pid 42 on api-1 ")

    async def test_a_long_title_widens_the_table(self, banner, caplog, monkeypatch):
        monkeypatch.setattr("app.core.startup.settings.APP_NAME", "A" * 90)

        table = _table(await _log(caplog))

        assert len({len(line) for line in table}) == 1
        assert "A" * 90 in table[1]

    async def test_on_a_color_terminal_the_state_is_colored(self, banner, caplog, monkeypatch):
        monkeypatch.setattr(startup, "ansi_enabled", lambda: True)

        table = _table(await _log(caplog, outbox_status="started"))

        assert len({len(ANSI.sub("", line)) for line in table}) == 1, "color takes no width"
        assert "\033[1mTestApp v1.0.0\033[0m" in table[1]
        assert f"\033[90m{V}\033[0m" in table[5], "the frame is grey"
        assert " \033[32m ok \033[0m " in table[5]
        # What is off recedes, its label and value too.
        assert " \033[90moff \033[0m " in table[8]
        assert " \033[90mDocs    \033[0m " in table[8]

    async def test_in_json_the_facts_are_fields_of_a_one_line_record(
        self, banner, caplog, monkeypatch
    ):
        monkeypatch.setattr(startup, "json_enabled", lambda: True)

        record = await _log(caplog)

        assert record is not None
        assert "\n" not in record.getMessage()
        assert record.getMessage().startswith("TestApp v1.0.0 | production | log DEBUG | pid ")
        line = json.loads(JSONFormatter().format(record))
        assert line["message"] == record.getMessage()
        assert line["startup"]["db"] == {
            "address": "db-host:5432",
            "name": "mydb",
            "status": "ok",
            "schema": ["0009"],
            "expected": ["0009"],
            "instance_max": 15,
            "capacity": CAPACITY,
            "pooler": False,
        }
        assert line["startup"]["rate_limit"]["default"] == "60/minute"

    @pytest.mark.parametrize(
        ("schema", "shown", "warned"),
        [
            (["0002"], "db-host:5432/mydb, schema 0002, code expects 0009", "is at 0002"),
            ([], "db-host:5432/mydb, no schema, code expects 0009", "is not migrated"),
        ],
    )
    async def test_a_schema_out_of_step_with_the_code_is_a_warning(
        self, banner, caplog, schema, shown, warned
    ):
        banner.return_value = schema

        record = await _log(caplog)

        assert _rows(record)[0] == ("warn", "Database", shown)
        warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert f"Database schema {warned} but this code expects 0009" in warnings[0]

    async def test_without_the_migrations_the_schema_is_shown_alone(
        self, banner, caplog, monkeypatch
    ):
        monkeypatch.setattr(startup, "expected_schema", lambda: None)

        record = await _log(caplog)

        assert _rows(record)[0] == (
            "ok",
            "Database",
            "db-host:5432/mydb, pool 5 + 10 overflow, timeout 30s, schema 0009",
        )
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    async def test_without_a_database_nothing_else_is_asked(self, banner, caplog):
        waiting = "waiting for the database"
        record = await _log(caplog, "UNAVAILABLE", outbox_status=waiting, jobs_status=waiting)

        rows = _rows(record)
        assert rows[0] == ("down", "Database", "db-host:5432/mydb, not answering")
        assert rows[1] == ("", "Capacity", "up to 16 from this instance")
        assert rows[2:4] == [("wait", "Outbox", waiting), ("wait", "Jobs", waiting)]
        # No database, no lock to take: connecting again would wait for a second timeout
        # during startup, when Ctrl+C cannot interrupt uvicorn.
        banner.assert_not_awaited()
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    async def test_the_other_processes_log_one_line(self, banner, caplog):
        record = await _log(caplog, acquired=False)

        assert record is None
        assert "Process ready (pid" in caplog.text
        banner.assert_not_awaited()

    @pytest.mark.parametrize(
        ("changes", "row"),
        [
            ({"DOCS_ENABLED": True}, ("on", "Docs", "/docs")),
            ({"METRICS_TOKEN": "t" * 32}, ("on", "Metrics", "/v1/metrics, token required")),
            ({"METRICS_ENABLED": False}, ("off", "Metrics", "")),
            ({"RATE_LIMIT_ENABLED": False}, ("off", "Limits", "")),
        ],
    )
    async def test_what_is_turned_on(self, banner, caplog, monkeypatch, changes, row):
        for name, value in changes.items():
            monkeypatch.setattr(f"app.core.startup.settings.{name}", value)

        record = await _log(caplog)

        assert row in _rows(record)
        assert "t" * 32 not in caplog.text

    async def test_workers_left_to_another_process(self, banner, caplog):
        record = await _log(caplog, outbox_status="disabled", jobs_status="disabled")

        assert _rows(record)[2:4] == [
            ("off", "Outbox", "not in this process"),
            ("off", "Jobs", "not in this process"),
        ]

    async def test_an_instance_that_can_exhaust_the_server_is_a_warning(
        self, banner, caplog, monkeypatch
    ):
        # 32 processes of 5 + 10 connections against 97 the server lets the app open.
        monkeypatch.setattr(startup, "_count_sibling_workers", lambda: 32)

        record = await _log(caplog)

        assert _rows(record)[1] == (
            "warn",
            "Capacity",
            "up to 480 from this instance, 12 of 100 in use",
        )
        assert record.fields["startup"]["db"]["capacity"] == CAPACITY

    async def test_behind_a_pooler_the_table_says_how_it_is_reached(
        self, banner, caplog, monkeypatch
    ):
        monkeypatch.setattr("app.core.startup.settings.DB_TRANSACTION_POOLER", True)
        engine = _mock_engine_with_advisory_lock(acquired=False)

        with caplog.at_level(logging.INFO, logger="app.core.startup"):
            await log_system_info(engine, "OK")

        record = next(r for r in caplog.records if hasattr(r, "fields"))
        rows = _rows(record)
        assert rows[1] == ("ok", "Pooler", "transaction mode, LISTEN and migrations direct")
        assert "Capacity" not in [label for _, label, _ in rows]
        assert record.fields["startup"]["db"]["pooler"] is True
        # A session lock through the pooler would stay on a lent connection: every process
        # prints its table, and the server's limit is the pooler's business.
        engine.connect.assert_not_called()
        startup.database_capacity.assert_not_awaited()

    async def test_the_title_counts_the_processes_when_there_are_several(
        self, banner, caplog, monkeypatch
    ):
        monkeypatch.setattr(startup, "_count_sibling_workers", lambda: 4)

        table = _table(await _log(caplog))

        assert table[1].strip().strip(V).rstrip().endswith(" | 4 processes")

    async def test_handles_url_without_host(self, banner, caplog, monkeypatch):
        monkeypatch.setattr("app.core.startup.settings.DATABASE_URL", "sqlite:///test.db")

        record = await _log(caplog)

        assert _rows(record)[0][2].startswith("unknown/test.db, pool")


class TestExpectedSchema:
    def test_is_the_last_migration_of_the_repo(self):
        # Migrations are numbered (--rev-id NNNN) and linear: the head is the highest one.
        versions = (startup.MIGRATIONS_DIR / "versions").glob("[0-9][0-9][0-9][0-9]_*.py")
        assert expected_schema() == [max(path.name[:4] for path in versions)]

    def test_none_where_the_migrations_are_not_shipped(self, monkeypatch, tmp_path):
        monkeypatch.setattr(startup, "MIGRATIONS_DIR", tmp_path / "missing")
        assert expected_schema() is None


class TestCheckUtcTimezone:
    def _run(self, monkeypatch, tzname, environment):
        monkeypatch.setattr("app.core.startup.time.tzname", tzname)
        monkeypatch.delenv("TZ", raising=False)
        monkeypatch.setattr("app.core.startup.settings.ENVIRONMENT", environment)
        check_utc_timezone()

    def test_utc_passes(self, monkeypatch):
        self._run(monkeypatch, ("UTC", "UTC"), "prod")

    def test_other_zone_fails_outside_local(self, monkeypatch):
        with pytest.raises(RuntimeError, match="not UTC"):
            self._run(monkeypatch, ("CET", "CEST"), "prod")

    def test_other_zone_only_warns_in_local(self, monkeypatch, caplog):
        with caplog.at_level(logging.WARNING, logger="app.core.startup"):
            self._run(monkeypatch, ("CET", "CEST"), "local")
        assert "not UTC" in caplog.text


class TestBannerLock:
    def test_siblings_share_the_id_and_other_servers_do_not(self, monkeypatch):
        # One banner per server (the workers of one uvicorn share a parent), not one for
        # the whole database: a fixed id let the oldest process silence every later one.
        from app.core import startup

        monkeypatch.setattr(startup.socket, "gethostname", lambda: "api-1")
        monkeypatch.setattr(startup.os, "getppid", lambda: 100)
        first = startup._banner_lock_id()
        assert startup._banner_lock_id() == first

        monkeypatch.setattr(startup.socket, "gethostname", lambda: "api-2")
        assert startup._banner_lock_id() != first
        assert -(2**63) <= first < 2**63  # fits the bigint pg_try_advisory_lock takes
