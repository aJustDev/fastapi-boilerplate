import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.core.events.handlers  # noqa: F401 — register all event handlers
from app.core.db import engine
from app.core.events.worker import OutboxWorker
from app.core.logging.config import setup_logging
from app.core.startup import check_database, log_system_info

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()

    db_status = await check_database(engine)
    app.state.ready = db_status == "OK"

    worker = OutboxWorker()
    if app.state.ready:
        await worker.start()
    app.state.outbox_worker = worker

    worker_status = "OK" if app.state.ready else "OFF (DB unavailable)"
    log_system_info(db_status, worker_status=worker_status)

    logger.info("Enjoy!")

    yield

    await worker.stop()
    app.state.ready = False
    await engine.dispose()
    logger.info("Shutdown complete")
