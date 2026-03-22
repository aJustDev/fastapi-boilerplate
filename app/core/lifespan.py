import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

import app.core.events.handlers  # noqa: F401 — register all event handlers
import app.core.jobs.handlers  # noqa: F401 — register all job handlers
from app.core.db import engine
from app.core.events.worker import OutboxWorker
from app.core.jobs.registry import job_registry
from app.core.jobs.worker import JobWorker
from app.core.logging.config import setup_logging
from app.core.startup import check_database, log_system_info

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()

    db_status = await check_database(engine)
    app.state.ready = db_status == "OK"

    worker = OutboxWorker()
    job_worker = JobWorker()
    if app.state.ready:
        await worker.start()
        await job_worker.start()
    app.state.outbox_worker = worker
    app.state.job_worker = job_worker

    worker_status = "OK" if app.state.ready else "OFF (DB unavailable)"
    job_worker_status = "OK" if app.state.ready else "OFF (DB unavailable)"
    await log_system_info(
        engine,
        db_status,
        worker_status=worker_status,
        job_worker_status=job_worker_status,
        registered_jobs=len(job_registry.registered_jobs),
    )

    yield

    await job_worker.stop()
    await worker.stop()
    app.state.ready = False
    await engine.dispose()
    logger.info("Shutdown complete")
