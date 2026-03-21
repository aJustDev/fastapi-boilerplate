import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.db import engine
from app.core.logging.config import setup_logging
from app.core.startup import check_database, log_system_info

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()

    db_status = await check_database(engine)
    log_system_info(db_status)

    app.state.ready = db_status == "OK"
    logger.info("Startup complete ✓")

    yield

    app.state.ready = False
    await engine.dispose()
    logger.info("Shutdown complete")
