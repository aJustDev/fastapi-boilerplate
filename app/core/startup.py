import asyncio
import logging
import os
import platform
import socket

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings

logger = logging.getLogger(__name__)

DB_CONNECT_TIMEOUT = 3
_BANNER_LOCK_ID = 2026_03_22  # arbitrary advisory lock ID


async def check_database(engine: AsyncEngine) -> str:
    try:
        async with asyncio.timeout(DB_CONNECT_TIMEOUT):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return "OK"
    except Exception as e:
        logger.warning(f"DB not available: {e!s}")
        return "UNAVAILABLE"


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
            except (OSError, IndexError, ValueError):
                continue
    except OSError:
        return 1
    return max(count, 1)


async def log_system_info(
    engine: AsyncEngine,
    db_status: str,
    *,
    worker_status: str = "OFF",
    job_worker_status: str = "OFF",
    registered_jobs: int = 0,
) -> None:
    pid = os.getpid()
    instances = _count_sibling_workers()

    # Only one process prints the full banner (advisory lock)
    is_banner_leader = False
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text(f"SELECT pg_try_advisory_lock({_BANNER_LOCK_ID})"))
            is_banner_leader = result.scalar()
    except Exception:
        is_banner_leader = True  # fallback: always print

    if is_banner_leader:
        hostname = socket.gethostname()
        os_info = f"{platform.system()} {platform.release()}"
        app_info = f"{settings.APP_NAME} v{settings.APP_VERSION}"
        env_info = settings.ENVIRONMENT.capitalize()
        log_level = settings.LOG_LEVEL.upper()

        db_host = (
            settings.DATABASE_URL.split("@")[-1].split("/")[0]
            if "@" in settings.DATABASE_URL
            else "unknown"
        )

        jobs_label = f"{registered_jobs} registered"
        instances_label = f"{instances} instance{'s' if instances > 1 else ''}"

        logger.info("========== SYSTEM CONFIGURATION ==========")
        logger.info(f"Host     : {hostname:<27} | OS     : {os_info}")
        logger.info(f"App      : {app_info:<27} | Env    : {env_info} ({log_level})")
        pool_info = f"{settings.DB_POOL_SIZE}+{settings.DB_MAX_OVERFLOW} (timeout {settings.DB_POOL_TIMEOUT}s)"

        logger.info(f"DB       : {db_host:<27} | Status : {db_status}")
        logger.info(f"Pool     : {pool_info:<27} | Pre-ping: ON")
        logger.info(f"EventBus : {'LISTEN/NOTIFY':<27} | Status : {worker_status}")
        logger.info(f"Jobs     : {jobs_label:<27} | Status : {job_worker_status}")
        logger.info(f"Workers  : {instances_label:<27} |")
        logger.info("===========================================")

    logger.info("Worker ready (PID=%d)", pid)
