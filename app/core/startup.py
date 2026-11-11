import asyncio
import hashlib
import logging
import multiprocessing
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
from app.core.startup_table import header, table

logger = logging.getLogger(__name__)

# Short on purpose: startup only decides whether to start the workers.
STARTUP_DB_CHECK_SECONDS = 3

# The migrations shipped with this code: inside the image next to app/, as in the repo.
MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


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


# Client connections, the ones max_connections limits. A role that is not a superuser sees
# no backend type for the sessions of other roles: for those, a session with a database and
# a user is taken for a client, which the server's own workers are not (a parallel or a
# replication worker is, so the count can run a little high while one lives).
_CAPACITY = text(
    "SELECT current_setting('max_connections')::int,"
    " current_setting('superuser_reserved_connections')::int,"
    " (SELECT count(*) FROM pg_stat_activity"
    " WHERE backend_type = 'client backend'"
    " OR (backend_type IS NULL AND datid IS NOT NULL AND usesysid IS NOT NULL))"
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
    """Processes of this server: this one and the workers uvicorn started next to it.

    Uvicorn starts the processes of `--workers` and `--reload` with multiprocessing, as
    children of one parent: they are counted in /proc, leaving out helpers like
    multiprocessing.resource_tracker. A process nobody started that way is alone, whatever
    else its parent runs (a shell with other jobs, an init with other services). Without
    /proc (macOS) the workers cannot be counted, and each one says 1.
    """
    if multiprocessing.parent_process() is None:
        return 1
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
            "pooler": settings.DB_TRANSACTION_POOLER,
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
        message = header(facts)
    else:
        color = ansi_enabled()
        message = "\n".join(["Startup summary", *table(facts, color=color)])
    logger.info(message, extra={"fields": {"startup": facts}})

    warning = _schema_warning(facts["db"])
    if warning:
        logger.warning(warning)
