import logging
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.core.exceptions.exceptions import AuthException, DomainException

logger = logging.getLogger(__name__)


_DIM = "\033[2m"
_CYAN = "\033[36m"
_YELLOW = "\033[33m"
_GREEN = "\033[32m"
_BLUE = "\033[34m"
_RED = "\033[31m"
_BOLD_RED = "\033[1;31m"
_RESET = "\033[0m"

_METHOD_COLORS = {
    "GET": _GREEN,
    "POST": _BLUE,
    "PATCH": _YELLOW,
    "PUT": _YELLOW,
    "DELETE": _RED,
}


def _status_color(code: int) -> str:
    if code < 300:
        return _GREEN
    if code < 400:
        return _CYAN
    if code < 500:
        return _YELLOW
    return _BOLD_RED


def _shorten_path(filepath: str) -> str:
    marker = "/app/"
    idx = filepath.find(marker)
    return filepath[idx + 1 :] if idx != -1 else filepath


def _extract_context(request: Request, exc: Exception) -> dict:
    tb = traceback.extract_tb(exc.__traceback__)
    last = tb[-1] if tb else None
    return {
        "exc_name": type(exc).__name__,
        "message": str(exc),
        "filename": _shorten_path(last.filename) if last else "unknown",
        "lineno": last.lineno if last else 0,
        "func": last.name if last else "unknown",
        "method": request.method,
        "path": request.url.path,
        "status_code": getattr(exc, "status_code", 500),
    }


def _format_log(ctx: dict) -> str:
    method = ctx["method"]
    mc = _METHOD_COLORS.get(method, _DIM)
    sc = _status_color(ctx["status_code"])
    return (
        f"{ctx['exc_name']}: {ctx['message']}\n"
        f"  {_DIM}Location:{_RESET} {_CYAN}{ctx['filename']}:{ctx['lineno']}{_RESET}"
        f" in {_YELLOW}{ctx['func']}(){_RESET}\n"
        f"  {_DIM}Request:{_RESET}  {mc}{method}{_RESET} {ctx['path']}\n"
        f"  {_DIM}Status:{_RESET}   {sc}{ctx['status_code']}{_RESET}"
    )


async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    ctx = _extract_context(request, exc)
    logger.warning(_format_log(ctx))
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=ctx["status_code"],
        content={"detail": ctx["message"]},
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "errors": errors},
    )


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = exc.detail.split()[-1] if exc.detail else ""
    logger.warning("Rate limit exceeded: %s %s (%s)", request.method, request.url.path, retry_after)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests"},
        headers={"Retry-After": retry_after},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    ctx = _extract_context(request, exc)
    logger.error(_format_log(ctx), exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AuthException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
