import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.db import engine
from app.core.events.worker import OutboxWorker
from app.core.jobs.registry import job_registry
from app.core.jobs.worker import JobWorker
from app.core.logging.config import setup_logging
from app.core.startup import check_database, check_utc_timezone, log_system_info

logger = logging.getLogger(__name__)


def _worker_status(enabled: bool, db_status: str) -> str:
    if not enabled:
        return "OFF (disabled)"
    return "OK" if db_status == "OK" else "WAITING (DB unavailable)"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    setup_logging()
    check_utc_timezone()

    # Only for the banner. A database that does not answer now is not a reason to give
    # up: the workers keep retrying on their own and readiness checks it on every call,
    # so the instance recovers as soon as the database does.
    db_status = await check_database(engine)

    worker = OutboxWorker()
    job_worker = JobWorker()
    if settings.OUTBOX_WORKER_ENABLED:
        await worker.start()
    if settings.JOB_WORKER_ENABLED:
        await job_worker.start()
    app.state.outbox_worker = worker
    app.state.job_worker = job_worker

    await log_system_info(
        engine,
        db_status,
        worker_status=_worker_status(settings.OUTBOX_WORKER_ENABLED, db_status),
        job_worker_status=_worker_status(settings.JOB_WORKER_ENABLED, db_status),
        registered_jobs=len(job_registry.registered_jobs),
    )
    app.state.ready = True

    yield

    app.state.ready = False
    await job_worker.stop()
    await worker.stop()
    await engine.dispose()
    logger.info("Shutdown complete")
