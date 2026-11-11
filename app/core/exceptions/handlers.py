import logging
import math
import os
import time
import traceback
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.core.exceptions.exceptions import AuthException, DomainException
from app.core.logging.middleware import record_error_code

logger = logging.getLogger(__name__)


def _error(
    request: Request,
    status_code: int,
    content: dict,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """The JSON error of the contract; its `code` is also named in the access line."""
    record_error_code(request.scope, content["code"])
    return JSONResponse(status_code=status_code, content=content, headers=headers)


# The code of the project: where an error is worth pointing at. The last frame of a
# traceback is often in a library (httpx, SQLAlchemy) or in a mock.
_ROOT = Path(__file__).resolve().parents[3]
_OUR_CODE = str(_ROOT / "app") + os.sep


def _raised_at(exc: BaseException) -> str:
    """The line of our code that raised it: `app/workshops/services/access.py:45 in ensure_visible()`."""
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [frame for frame in frames if frame.filename.startswith(_OUR_CODE)]
    if not (ours or frames):
        return "unknown place"
    frame = (ours or frames)[-1]
    where = Path(frame.filename)
    shown = where.relative_to(_ROOT) if where.is_relative_to(_ROOT) else where
    return f"{shown}:{frame.lineno} in {frame.name}()"


async def domain_exception_handler(request: Request, exc: DomainException) -> JSONResponse:
    # A 4xx is the API answering a client as it should: the access line names its code,
    # and where it was raised is a detail for whoever is debugging. A 5xx is ours.
    status_code = exc.status_code
    level = logging.ERROR if status_code >= 500 else logging.DEBUG
    logger.log(level, "%s: %s (%s)", type(exc).__name__, exc, _raised_at(exc))
    headers = getattr(exc, "headers", None) or {}
    return _error(request, status_code, {"detail": str(exc), "code": exc.code}, headers)


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
    return _error(
        request,
        exc.status_code,
        {"detail": exc.detail, "code": _HTTP_CODES.get(exc.status_code, "http_error")},
        getattr(exc, "headers", None),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()]
    logger.debug("Validation error: %s", "; ".join(errors))
    return _error(
        request, 422, {"detail": "Validation error", "code": "validation_error", "errors": errors}
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
    logger.warning(
        "Rate limit %s exceeded by %s on %s %s, retry in %ss",
        exc.detail,
        request.client.host if request.client else "unknown client",
        request.method,
        request.url.path,
        retry_after,
    )
    return _error(
        request,
        429,
        {"detail": "Too many requests", "code": "rate_limited"},
        {"Retry-After": retry_after},
    )


# SQLSTATE codes (PostgreSQL appendix A). Class 23 is integrity constraint violation,
# class 22 is data exception: a value the column type cannot take.
_NOT_NULL_VIOLATION = "23502"
_CHECK_VIOLATION = "23514"
_DATA_EXCEPTION_CLASS = "22"
# The transaction lost to another one and nothing of it was stored: a lock not granted
# within lock_timeout, a deadlock, a serialization failure. The same request, sent again,
# is expected to work.
_LOST_TO_ANOTHER_TRANSACTION = frozenset({"55P03", "40P01", "40001"})


def _driver_error(exc: DBAPIError) -> BaseException | None:
    """The asyncpg exception behind a SQLAlchemy DBAPIError."""
    return exc.orig.__cause__ if exc.orig is not None else None


def _log_rejected_by_database(request: Request, exc: DBAPIError, status_code: int) -> None:
    # One line, and nothing of the message PostgreSQL wrote: its DETAIL quotes the
    # offending values ("Key (lower(email))=(a@b.c) already exists").
    driver_error = _driver_error(exc)
    logger.warning(
        "%s %s -> %d: the database rejected the statement (%s, sqlstate=%s, constraint=%s)",
        request.method,
        request.url.path,
        status_code,
        type(driver_error or exc.orig).__name__,
        getattr(exc.orig, "sqlstate", None),
        getattr(driver_error, "constraint_name", None),
    )


def _invalid_input_response(request: Request) -> JSONResponse:
    return _error(
        request,
        422,
        {
            "detail": "Validation error",
            "code": "invalid_input",
            "errors": ["a value was rejected by the database"],
        },
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    # Safety net for constraint violations that slip past validation and the checks in
    # the services (two requests racing between the SELECT and the INSERT). Without it
    # they would end as a 500 and an alert, while the client simply sent something the
    # schema does not allow. A missing or out-of-range value is a 422; a duplicate or a
    # broken reference is a conflict with what is already stored.
    if getattr(exc.orig, "sqlstate", None) in (_NOT_NULL_VIOLATION, _CHECK_VIOLATION):
        _log_rejected_by_database(request, exc, 422)
        return _invalid_input_response(request)
    _log_rejected_by_database(request, exc, 409)
    return _error(
        request, 409, {"detail": "Conflict with existing resource", "code": "integrity_conflict"}
    )


def _is_data_error(exc: DBAPIError) -> bool:
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if isinstance(sqlstate, str) and sqlstate.startswith(_DATA_EXCEPTION_CLASS):
        return True
    # asyncpg refuses some values before sending them (an int beyond the column type):
    # no SQLSTATE, but the same kind of error.
    return isinstance(_driver_error(exc), asyncpg.DataError)


async def database_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    """A value PostgreSQL or the driver could not take is the client's error: 422.

    Request validation should have stopped it (app/core/schema.py); this is the net for
    the field that was left unbounded. A transaction that lost to another one is nobody's
    error: 503 with Retry-After. Every other database error is ours: it is raised again
    and ends as a 500.
    """
    if getattr(exc.orig, "sqlstate", None) in _LOST_TO_ANOTHER_TRANSACTION:
        _log_rejected_by_database(request, exc, 503)
        return _error(
            request,
            503,
            {"detail": "The resource is busy, try again", "code": "busy"},
            {"Retry-After": "1"},
        )
    if not _is_data_error(exc):
        raise exc
    _log_rejected_by_database(request, exc, 422)
    return _invalid_input_response(request)


def describe_unhandled(request: Request, exc: Exception) -> str:
    """Log message of an unhandled error, logged with its traceback: the exception, where
    it was raised and the request."""
    message = f": {exc}" if str(exc) else ""
    return (
        f"Unhandled {type(exc).__name__}{message} ({_raised_at(exc)}, "
        f"{request.method} {request.url.path})"
    )


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
    record_error_code(request.scope, "internal_error")
    return internal_error_response()


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AuthException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DomainException, domain_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DBAPIError, database_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
