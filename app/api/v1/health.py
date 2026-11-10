import asyncio
import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.core.db import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


class HealthStatus(BaseModel):
    status: str = Field(description="`alive`, `ready`, `not ready` or `database unavailable`")


@router.get("/health/liveness", response_model=HealthStatus)
async def liveness():
    """The process is up and serving requests. It does not look at the database."""
    return {"status": "alive"}


# A probe must answer quickly: without a limit of its own it would wait for the pool
# (DB_POOL_TIMEOUT) or for a connection attempt (DB_CONNECT_TIMEOUT).
READINESS_DB_CHECK_SECONDS = 2


@router.get(
    "/health/readiness",
    response_model=HealthStatus,
    responses={503: {"model": HealthStatus, "description": "Not ready to serve requests"}},
)
async def readiness(request: Request):
    """Whether this instance can serve requests right now.

    `ready` is false only while the process starts or shuts down. The database is asked
    on every call, so an instance that lost it (or started without it) is taken out of
    rotation and comes back by itself when the database does.
    """
    ready = getattr(request.app.state, "ready", False)
    if not ready:
        return JSONResponse(status_code=503, content={"status": "not ready"})

    try:
        async with asyncio.timeout(READINESS_DB_CHECK_SECONDS):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
    except Exception:
        # The 503 is read by the orchestrator, not a person: without this line the
        # reason why the instance stopped being ready is recorded nowhere.
        logger.warning("Readiness check failed", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "database unavailable"})

    return {"status": "ready"}
