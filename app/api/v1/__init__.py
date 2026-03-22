from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.health import router as health_router
from app.api.v1.items import router as items_router
from app.api.v1.metrics import router as metrics_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth_router)
v1_router.include_router(items_router)
v1_router.include_router(health_router)
v1_router.include_router(metrics_router)
