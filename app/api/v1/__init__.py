from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.metrics import router as metrics_router
from app.auth.api.router import router as auth_router
from app.workshops.api.router import me_router as workshops_me_router
from app.workshops.api.router import router as workshops_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(auth_router)
v1_router.include_router(workshops_router)
v1_router.include_router(workshops_me_router)
v1_router.include_router(health_router)
v1_router.include_router(metrics_router)
