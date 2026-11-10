import secrets
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.core.config import settings
from app.core.db import engine
from app.core.exceptions import AuthenticationError
from app.core.metrics.db_collector import update_db_pool_metrics

router = APIRouter(tags=["Observability"])

_bearer = HTTPBearer(auto_error=False)


def _scraper(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> None:
    """With METRICS_TOKEN set, the scrape has to present it as a bearer token."""
    if not settings.METRICS_TOKEN:
        return
    presented = credentials.credentials if credentials else ""
    if not secrets.compare_digest(presented.encode(), settings.METRICS_TOKEN.encode()):
        raise AuthenticationError("Invalid metrics token")


@router.get("/metrics", include_in_schema=False, dependencies=[Depends(_scraper)])
async def metrics():
    update_db_pool_metrics(engine)
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
