import logging
import math
import time
import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.core.exceptions.exceptions import AuthException, DomainException
from app.core.logging.config import ansi_enabled

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
    # Color is decided here, not in a Formatter, because this message is already
    # built when the formatter runs: JSONFormatter would ship the escape codes
    # inside the `message` field.
    codes = (
        _DIM,
        _RESET,
        _CYAN,
        _YELLOW,
        _METHOD_COLORS.get(method, _DIM),
        _status_color(ctx["status_code"]),
    )
    dim, reset, cyan, yellow, mc, sc = codes if ansi_enabled() else ("",) * len(codes)
    return (
        f"{ctx['exc_name']}: {ctx['message']}\n"
        f"  {dim}Location:{reset} {cyan}{ctx['filename']}:{ctx['lineno']}{reset}"
        f" in {yellow}{ctx['func']}(){reset}\n"
        f"  {dim}Request:{reset}  {mc}{method}{reset} {ctx['path']}\n"
        f"  {dim}Status:{reset}   {sc}{ctx['status_code']}{reset}"
    )


async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    ctx = _extract_context(request, exc)
    logger.warning(_format_log(ctx))
    headers = getattr(exc, "headers", None) or {}
    return JSONResponse(
        status_code=ctx["status_code"],
        content={"detail": ctx["message"], "code": exc.code},
        headers=headers,
    )


# `code` for errors that are not a DomainException: 404 of an unknown route, 405 of a
# wrong method, and HTTPExceptions raised by hand. Same vocabulary as exceptions.py on
# purpose, so a missing route and a missing resource read the same to a client.
_HTTP_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": _HTTP_CODES.get(exc.status_code, "http_error")},
        headers=getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    logger.warning("Validation error on %s %s: %s", request.method, request.url.path, errors)
    return JSONResponse(
        status_code=422,
        content={"detail": "Validation error", "code": "validation_error", "errors": errors},
    )


def _retry_after_seconds(request: Request, exc: RateLimitExceeded) -> int:
    """Seconds until the window of the limit that was hit opens again.

    slowapi leaves the limit and its key in `request.state.view_rate_limit` before
    raising; with them the storage tells how long is left. Without that state, the
    whole window, which is a valid upper bound for Retry-After.
    """
    view = getattr(request.state, "view_rate_limit", None)
    app = request.scope.get("app")
    limiter = getattr(app.state, "limiter", None) if app is not None else None
    if view is not None and limiter is not None:
        item, identifiers = view
        reset_at, _ = limiter.limiter.get_window_stats(item, *identifiers)
        remaining: int = math.ceil(reset_at - time.time())
        if remaining > 0:
            return remaining
    expiry: int = exc.limit.limit.get_expiry() if exc.limit is not None else 60
    return expiry


async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    retry_after = str(_retry_after_seconds(request, exc))
    logger.warning("Rate limit exceeded: %s %s (%s)", request.method, request.url.path, retry_after)
    return JSONResponse(
        status_code=429,
        content={"detail": "Too many requests", "code": "rate_limited"},
        headers={"Retry-After": retry_after},
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Safety net for constraint violations that slip past the checks in the services
    # (two requests racing between the SELECT and the INSERT). Without it they would
    # end as a 500 and an alert, while the client simply sent a duplicate.
    ctx = _extract_context(request, exc)
    ctx["status_code"] = 409
    logger.warning(_format_log(ctx), exc_info=True)
    return JSONResponse(
        status_code=409,
        content={"detail": "Conflict with existing resource", "code": "integrity_conflict"},
    )


def describe_unhandled(request: Request, exc: Exception) -> str:
    """Log message of an unhandled error: exception, where it was raised and the request."""
    return _format_log(_extract_context(request, exc))


def internal_error_response() -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "code": "internal_error"},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Last resort. Errors raised under the middleware stack never get here:
    # UnhandledErrorMiddleware answers them from inside it. This one only sees what a
    # middleware itself raises.
    logger.error(describe_unhandled(request, exc), exc_info=True)
    return internal_error_response()


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AuthException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
