from fastapi import FastAPI

import app.models  # noqa: F401 — ensure all ORM models are registered
from app.api.v1 import v1_router
from app.core.config import settings
from app.core.exceptions.handlers import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.middleware import register_middleware

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    root_path=settings.ROOT_PATH,
    lifespan=lifespan,
    swagger_ui_parameters={
        "persistAuthorization": True,
        "defaultModelsExpandDepth": -1,
        "filter": True,
        "displayRequestDuration": True,
        "tryItOutEnabled": True,
    }
)

register_exception_handlers(app)
register_middleware(app)
app.include_router(v1_router)
