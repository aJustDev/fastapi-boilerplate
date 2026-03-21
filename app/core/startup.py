import asyncio
import logging
import platform
import socket

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings

logger = logging.getLogger(__name__)

DB_CONNECT_TIMEOUT = 3


async def check_database(engine: AsyncEngine) -> str:
    try:
        async with asyncio.timeout(DB_CONNECT_TIMEOUT):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return "OK"
    except Exception as e:
        logger.warning(f"DB not available: {e!s}")
        return "UNAVAILABLE"


def log_system_info(db_status: str, *, worker_status: str = "OFF") -> None:
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

    logger.info("========== SYSTEM CONFIGURATION ==========")
    logger.info(f"Host     : {hostname:<27} | OS     : {os_info}")
    logger.info(f"App      : {app_info:<27} | Env    : {env_info} ({log_level})")
    logger.info(f"DB       : {db_host:<27} | Status : {db_status}")
    logger.info(f"Worker   : {'Outbox (LISTEN/NOTIFY)':<27} | Status : {worker_status}")
    logger.info("===========================================")
