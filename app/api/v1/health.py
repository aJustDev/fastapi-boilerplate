import logging

from fastapi import APIRouter, Request
from sqlalchemy import text
from starlette.responses import JSONResponse

from app.core.db import engine

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health/liveness")
async def liveness():
    return {"status": "alive"}


@router.get("/health/readiness")
async def readiness(request: Request):
    ready = getattr(request.app.state, "ready", False)
    if not ready:
        return JSONResponse(status_code=503, content={"status": "not ready"})

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        # The 503 is read by the orchestrator, not a person: without this line the
        # reason why the instance stopped being ready is recorded nowhere.
        logger.warning("Readiness check failed", exc_info=True)
        return JSONResponse(status_code=503, content={"status": "database unavailable"})

    return {"status": "ready"}
