from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.core.db import engine
from app.core.metrics.db_collector import update_db_pool_metrics

router = APIRouter(tags=["Observability"])


@router.get("/metrics", include_in_schema=False)
async def metrics():
    update_db_pool_metrics(engine)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
