from fastapi import FastAPI

import app.db_registry as _db_registry  # noqa: F401 -- models and handlers, before the app
from app.api.v1 import v1_router
from app.core.config import settings
from app.core.exceptions.handlers import register_exception_handlers
from app.core.exceptions.schemas import ERROR_RESPONSES
from app.core.lifespan import lifespan
from app.core.logging.config import setup_logging
from app.core.middleware import register_middleware


def create_app() -> FastAPI:
    setup_logging()
    # Swagger UI, ReDoc and the OpenAPI document are served only when asked for.
    docs = {} if settings.DOCS_ENABLED else {"docs_url": None, "redoc_url": None}
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=settings.APP_DESCRIPTION,
        lifespan=lifespan,
        responses=ERROR_RESPONSES,
        openapi_url="/openapi.json" if settings.DOCS_ENABLED else None,
        swagger_ui_parameters={
            "persistAuthorization": True,
            "defaultModelsExpandDepth": -1,
            "filter": True,
            "displayRequestDuration": True,
            "tryItOutEnabled": True,
        },
        **docs,  # type: ignore[arg-type]
    )
    register_exception_handlers(application)
    register_middleware(application)
    application.include_router(v1_router)
    return application


app = create_app()
