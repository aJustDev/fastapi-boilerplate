import asyncio
import hashlib
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any

from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings
from app.core.logging.config import ansi_enabled, json_enabled
from app.core.logging.errors import one_line
from app.core.logging.middleware import METRICS_PATH

logger = logging.getLogger(__name__)

# Short on purpose: startup only decides whether to start the workers.
STARTUP_DB_CHECK_SECONDS = 3

# The migrations shipped with this code: inside the image next to app/, as in the repo.
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# What main.py serves when DOCS_ENABLED is set.
DOCS_PATH = "/docs"


def _banner_lock_id() -> int:
    """Advisory lock id shared by the sibling processes of one server, and only by them.

    The lock is taken on a pooled connection and lives as long as that connection: with
    one fixed id for everybody, the first process to start would silence the banner of
    every later one, the next deployment included.
    """
    siblings = f"{socket.gethostname()}:{os.getppid()}".encode()
    return int.from_bytes(hashlib.sha256(siblings).digest()[:8], "big", signed=True)


def check_utc_timezone() -> None:
    """The process must run in UTC: fail outside local, warn in local.

    A naive datetime sent to a `timestamptz` parameter is interpreted in the time zone
    of the process. If that differs between environments, the same request writes or
    compares different instants. The Docker image and CI set TZ=UTC.
    """
    local_tz = (time.tzname[0] or "").upper() if time.tzname else ""
    env_tz = (os.environ.get("TZ") or "").upper()
    if local_tz in {"UTC", "GMT", "UCT", "UNIVERSAL", ""} or env_tz == "UTC":
        return

    message = f"Process time zone is not UTC (tzname={time.tzname}, TZ={env_tz}). Set TZ=UTC."
    if settings.ENVIRONMENT != "local":
        raise RuntimeError(message)
    logger.warning(message)


async def check_database(engine: AsyncEngine) -> str:
    try:
        async with asyncio.timeout(STARTUP_DB_CHECK_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return "OK"
    # The message carries the error; the traceback of a "connection refused" at
    # startup adds nothing.
    except Exception as e:  # noqa: BLE001
        # The type too, and a reason where the message is empty (a timeout).
        reason = str(e) or f"no answer in {STARTUP_DB_CHECK_SECONDS}s"
        logger.warning("Database not available: %s: %s", type(e).__name__, reason)
        return "UNAVAILABLE"


def expected_schema() -> list[str] | None:
    """Head revisions of the migrations shipped with this code; None without them."""
    if not MIGRATIONS_DIR.is_dir():
        return None
    return sorted(ScriptDirectory(str(MIGRATIONS_DIR)).get_heads())


async def database_schema(engine: AsyncEngine) -> list[str] | None:
    """Revisions the database is at: empty if it was never migrated, None if unknown."""
    try:
        async with engine.connect() as conn:
            heads = await conn.run_sync(
                lambda sync_conn: MigrationContext.configure(sync_conn).get_current_heads()
            )
        return sorted(heads)
    # The banner must not stop the startup; without the revision it says less.
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read the schema version: %s: %s", type(e).__name__, e)
        return None


_CAPACITY = text(
    "SELECT current_setting('max_connections')::int,"
    " current_setting('superuser_reserved_connections')::int,"
    " (SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend')"
)


async def database_capacity(engine: AsyncEngine) -> dict[str, int] | None:
    """The connections the server takes and the ones in use; None if unknown."""
    try:
        async with engine.connect() as conn:
            limit, reserved, in_use = (await conn.execute(_CAPACITY)).one()
        return {"max": limit, "reserved": reserved, "in_use": in_use}
    # The banner must not stop the startup; without the numbers it says less.
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not read the connection limits: %s", one_line(e))
        return None


def _count_sibling_workers() -> int:
    """Count uvicorn worker processes (siblings sharing the same PPID).

    Excludes helper processes like multiprocessing.resource_tracker.
    """
    my_ppid = os.getppid()
    count = 0
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == my_ppid:
                continue
            try:
                with open(f"/proc/{entry}/stat") as f:
                    ppid = int(f.read().split()[3])
                if ppid != my_ppid:
                    continue
                with open(f"/proc/{entry}/cmdline") as f:
                    cmdline = f.read()
                if "resource_tracker" in cmdline:
                    continue
                count += 1
            except OSError, IndexError, ValueError:
                continue
    except OSError:
        return 1
    return max(count, 1)


def _facts(
    db_status: str,
    schema: list[str] | None,
    expected: list[str] | None,
    *,
    outbox_status: str,
    jobs_status: str,
    registered_jobs: int,
    processes: int,
    capacity: dict[str, int] | None = None,
) -> dict[str, Any]:
    url = make_url(settings.DATABASE_URL)
    address = url.host or "unknown"
    if url.port:
        address = f"{address}:{url.port}"
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "env": settings.ENVIRONMENT,
        "log_level": settings.LOG_LEVEL.upper(),
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "processes": processes,
        "db": {
            "address": address,
            "name": url.database or "",
            "status": "ok" if db_status == "OK" else "unavailable",
            "schema": schema,
            "expected": expected,
            # Each process: its pool, its overflow and the LISTEN of the outbox worker.
            "instance_max": processes
            * (settings.DB_POOL_SIZE + settings.DB_MAX_OVERFLOW + (outbox_status != "disabled")),
            "capacity": capacity,
            "pooler": {
                "transaction": settings.DB_TRANSACTION_POOLER,
                "direct_url": bool(settings.DB_DIRECT_URL),
            },
        },
        "pool": {
            "size": settings.DB_POOL_SIZE,
            "overflow": settings.DB_MAX_OVERFLOW,
            "timeout_s": settings.DB_POOL_TIMEOUT,
        },
        "outbox": outbox_status,
        "jobs": {"status": jobs_status, "handlers": registered_jobs},
        "rate_limit": {
            "enabled": settings.RATE_LIMIT_ENABLED,
            "default": settings.RATE_LIMIT_DEFAULT,
            "strict": settings.RATE_LIMIT_STRICT,
            "storage": "memory",
        },
        "docs": settings.DOCS_ENABLED,
        "metrics": {"enabled": settings.METRICS_ENABLED, "token": bool(settings.METRICS_TOKEN)},
    }


# The state column: green when it works, yellow when it needs a look, red when it does not
# work, grey for what is turned off. SGR codes, used only on a color terminal.
_TONES = {"ok": "32", "on": "36", "wait": "33", "warn": "33", "down": "31", "off": "90"}
_WORKER_STATES = {"started": "ok", "waiting for the database": "wait", "disabled": "off"}
_WORKER_VALUES = {"wait": "waiting for the database", "off": "not in this process"}


def _paint(text: str, sgr: str, color: bool) -> str:
    return f"\033[{sgr}m{text}\033[0m" if color and sgr else text


def _about(facts: dict[str, Any]) -> str:
    parts = [facts["env"], f"log {facts['log_level']}", f"pid {facts['pid']} on {facts['host']}"]
    if facts["processes"] > 1:
        parts.append(f"{facts['processes']} processes")
    return " | ".join(parts)


def _header(facts: dict[str, Any]) -> str:
    """The startup log in one line: the message of the JSON record."""
    return f"{facts['app']} v{facts['version']} | {_about(facts)}"


def _database(db: dict[str, Any], pool: dict[str, Any]) -> tuple[str, str]:
    where = f"{db['address']}/{db['name']}"
    if db["status"] != "ok":
        return "down", f"{where}, not answering"
    schema, expected = db["schema"], db["expected"]
    current = f"schema {', '.join(schema)}" if schema else "no schema"
    if schema is not None and expected is not None and schema != expected:
        return "warn", f"{where}, {current}, code expects {', '.join(expected)}"
    # A schema that matches the code is what `ok` says; the revision is shown only when there
    # is nothing to compare it with.
    shown = f", {current}" if schema is not None and expected is None else ""
    pool_size = f"pool {pool['size']} + {pool['overflow']} overflow, timeout {pool['timeout_s']}s"
    return "ok", f"{where}, {pool_size}{shown}"


def _connections(db: dict[str, Any]) -> tuple[str, str]:
    """Whether this instance alone fits in what the server takes (it cannot see replicas)."""
    reach = f"up to {db['instance_max']} from this instance"
    capacity = db["capacity"]
    if capacity is None:
        return "", reach
    allowed = capacity["max"] - capacity["reserved"]
    state = "warn" if db["instance_max"] > allowed else "ok"
    return state, f"{reach}, {capacity['in_use']} of {capacity['max']} in use"


def _pooler(db: dict[str, Any]) -> tuple[str, str]:
    if db["pooler"]["direct_url"]:
        return "ok", "transaction mode, LISTEN and migrations direct"
    return "warn", (
        f"transaction mode, no DB_DIRECT_URL: events by polling every "
        f"{settings.OUTBOX_POLL_INTERVAL_SECONDS}s"
    )


def _worker(status: str, running: str) -> tuple[str, str]:
    state = _WORKER_STATES[status]
    return state, _WORKER_VALUES.get(state, running)


def _switch(enabled: bool, value: str) -> tuple[str, str]:
    return ("on", value) if enabled else ("off", "")


def _rows(facts: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(state, label, value) of each line."""
    limits, metrics = facts["rate_limit"], facts["metrics"]
    token = "token required" if metrics["token"] else "no token"
    lines = {
        "Database": _database(facts["db"], facts["pool"]),
        # Behind a pooler the server's limit is the pooler's business, not this budget.
        **(
            {"Pooler": _pooler(facts["db"])}
            if facts["db"]["pooler"]["transaction"]
            else {"Capacity": _connections(facts["db"])}
        ),
        "Outbox": _worker(facts["outbox"], "listening for events"),
        "Jobs": _worker(facts["jobs"]["status"], f"{facts['jobs']['handlers']} handlers"),
        "Limits": _switch(
            limits["enabled"],
            f"{limits['default']}, strict {limits['strict']}, in memory per process",
        ),
        "Docs": _switch(facts["docs"], DOCS_PATH),
        "Metrics": _switch(metrics["enabled"], f"{METRICS_PATH}, {token}"),
    }
    return [(state, label, value) for label, (state, value) in lines.items()]


# Box drawing for the table; it is printed only in the text formats.
_H, _V = "\u2500", "\u2502"
_TOP, _BOTTOM = ("\u250c", "\u2510"), ("\u2514", "\u2534", "\u2518")
_SPLIT = ("\u251c", "\u252c", "\u2524")
_STATE_WIDTH = 4


def _table(facts: dict[str, Any], *, color: bool = False) -> list[str]:
    """The startup log as a framed table: a title line, then one row per piece."""
    rows = _rows(facts)
    title, about = f"{facts['app']} v{facts['version']}", _about(facts)
    label_width = max(len(label) for _, label, _ in rows)
    # Inner width: the three columns with one space of padding each side and the two
    # separators between them, widened if the title line needs more.
    columns = _STATE_WIDTH + 2 + label_width + 2 + 2
    value_width = max(max(len(value) for *_, value in rows), len(title) + len(about) + 5 - columns)
    widths = [_STATE_WIDTH + 2, label_width + 2, value_width + 2]
    inner = sum(widths) + 2

    def frame(text: str) -> str:  # the frame recedes; the content is what is read
        return _paint(text, "90", color)

    gap = " " * (inner - 2 - len(title) - len(about))
    lines = [
        frame(_TOP[0] + _H * inner + _TOP[1]),
        f"{frame(_V)} {_paint(title, '1', color)}{gap}{about} {frame(_V)}",
        frame(_SPLIT[0] + _SPLIT[1].join(_H * w for w in widths) + _SPLIT[2]),
    ]
    for state, label, value in rows:
        tone = "90" if state == "off" else ""  # what is turned off recedes too
        cells = [
            _paint(f"{state:^{_STATE_WIDTH}}", _TONES.get(state, ""), color),
            _paint(f"{label:<{label_width}}", tone, color),
            _paint(f"{value:<{value_width}}", tone, color),
        ]
        lines.append(frame(_V) + frame(_V).join(f" {cell} " for cell in cells) + frame(_V))
    lines.append(frame(_BOTTOM[0] + _BOTTOM[1].join(_H * w for w in widths) + _BOTTOM[2]))
    return [f"  {line}" for line in lines]


def _schema_warning(db: dict[str, Any]) -> str | None:
    schema, expected = db["schema"], db["expected"]
    if schema is None or expected is None or schema == expected:
        return None
    current = f"at {', '.join(schema)}" if schema else "not migrated"
    return (
        f"Database schema is {current} but this code expects {', '.join(expected)}: "
        "run `alembic upgrade head`, or deploy the code that matches the database"
    )


async def log_system_info(
    engine: AsyncEngine,
    db_status: str,
    *,
    outbox_status: str = "disabled",
    jobs_status: str = "disabled",
    registered_jobs: int = 0,
) -> None:
    pid = os.getpid()
    processes = _count_sibling_workers()

    # Only one process prints the full banner (advisory lock). Without a database there is
    # no lock to take: trying would wait for another connection timeout during startup,
    # when uvicorn cannot be interrupted, so every process prints it. Behind a pooler in
    # transaction mode a session lock stays on a server connection lent to others, so
    # every process prints it too.
    is_banner_leader = True
    if db_status == "OK" and not settings.DB_TRANSACTION_POOLER:
        try:
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _banner_lock_id()}
                )
                is_banner_leader = bool(result.scalar())
        # The lock only decides who prints the banner; if it fails, every process
        # prints it, which is visible on its own.
        except Exception:  # noqa: BLE001
            is_banner_leader = True

    if not is_banner_leader:
        logger.info("Process ready (pid %d)", pid)
        return

    schema = await database_schema(engine) if db_status == "OK" else None
    direct = db_status == "OK" and not settings.DB_TRANSACTION_POOLER
    capacity = await database_capacity(engine) if direct else None
    facts = _facts(
        db_status,
        schema,
        expected_schema(),
        outbox_status=outbox_status,
        jobs_status=jobs_status,
        registered_jobs=registered_jobs,
        processes=processes,
        capacity=capacity,
    )
    # One line in JSON, where the facts travel as fields; a short table on a terminal.
    if json_enabled():
        message = _header(facts)
    else:
        color = ansi_enabled()
        message = "\n".join(["Startup summary", *_table(facts, color=color)])
    logger.info(message, extra={"fields": {"startup": facts}})

    warning = _schema_warning(facts["db"])
    if warning:
        logger.warning(warning)
