import logging
from unittest.mock import MagicMock

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from limits import parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit
from starlette.datastructures import URL

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError, RepoException
from app.core.exceptions.exceptions import DomainException
from app.core.exceptions.handlers import (
    domain_exception_handler,
    rate_limit_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


def _limit() -> Limit:
    return Limit(
        limit=parse("1/minute"),
        key_func=lambda: "k",
        scope=None,
        per_method=False,
        methods=None,
        error_message=None,
        exempt_when=None,
        cost=1,
        override_defaults=False,
    )


def _make_request(method: str = "GET", path: str = "/test") -> MagicMock:
    request = MagicMock(spec=Request)
    request.method = method
    request.url = MagicMock(spec=URL)
    request.url.path = path
    request.scope = {}
    return request


class TestDomainExceptionHandler:
    async def test_not_found_returns_404(self):
        request = _make_request()
        exc = NotFoundError("Order", 42)

        response = await domain_exception_handler(request, exc)

        assert response.status_code == 404
        assert b"Order not found" in response.body

    async def test_conflict_returns_409(self):
        request = _make_request()
        exc = ConflictError("User", "email already exists")

        response = await domain_exception_handler(request, exc)

        assert response.status_code == 409
        assert b"Conflict on User" in response.body

    async def test_authentication_error_returns_401_with_header(self):
        request = _make_request()
        exc = AuthenticationError("Invalid token")

        response = await domain_exception_handler(request, exc)

        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"
        assert b"Invalid token" in response.body


class TestValidationExceptionHandler:
    async def test_returns_422(self):
        request = _make_request("POST", "/orders")
        exc = RequestValidationError(
            errors=[
                {
                    "type": "missing",
                    "loc": ("body", "name"),
                    "msg": "Field required",
                    "input": {},
                }
            ]
        )

        response = await validation_exception_handler(request, exc)

        assert response.status_code == 422
        assert b"Validation error" in response.body


class TestUnhandledExceptionHandler:
    async def test_returns_500(self):
        request = _make_request()
        exc = RuntimeError("Something broke")

        response = await unhandled_exception_handler(request, exc)

        assert response.status_code == 500
        assert b"Internal server error" in response.body


def _raised(exc: DomainException) -> DomainException:
    """The exception with a traceback, as a handler receives it."""
    try:
        raise exc
    except DomainException as raised:
        return raised


class TestWhatIsLogged:
    """A 4xx is the API answering as it should: one DEBUG line. A 5xx is an ERROR."""

    async def test_a_client_error_is_one_debug_line_with_where_it_was_raised(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="app.core.exceptions.handlers"):
            await domain_exception_handler(_make_request(), _raised(NotFoundError("Order", 42)))

        [record] = caplog.records
        assert record.levelno == logging.DEBUG
        assert record.getMessage().startswith("NotFoundError: Order not found (ID: 42) (")
        assert "test_exception_handlers.py:" in record.getMessage()
        assert "\n" not in record.getMessage()

    async def test_a_domain_error_of_ours_is_an_error(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="app.core.exceptions.handlers"):
            await domain_exception_handler(_make_request(), _raised(RepoException("lost")))

        [record] = caplog.records
        assert record.levelno == logging.ERROR

    async def test_validation_errors_are_joined(self, caplog):
        exc = RequestValidationError(
            [
                {"loc": ("body", "a"), "msg": "Field required", "type": "missing"},
                {"loc": ("body", "b"), "msg": "Field required", "type": "missing"},
            ]
        )
        with caplog.at_level(logging.DEBUG, logger="app.core.exceptions.handlers"):
            await validation_exception_handler(_make_request("POST", "/orders"), exc)

        [record] = caplog.records
        assert record.levelno == logging.DEBUG
        assert record.getMessage() == (
            "Validation error: body.a: Field required; body.b: Field required"
        )

    async def test_a_rate_limit_says_who_where_and_when_to_retry(self, caplog):
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/v1/auth/login",
            "headers": [],
            "query_string": b"",
            "client": ("203.0.113.7", 50000),
        }
        with caplog.at_level(logging.DEBUG, logger="app.core.exceptions.handlers"):
            await rate_limit_exception_handler(Request(scope), RateLimitExceeded(_limit()))

        [record] = caplog.records
        assert record.levelno == logging.WARNING
        assert record.getMessage() == (
            "Rate limit 1 per 1 minute exceeded by 203.0.113.7 on POST /v1/auth/login, retry in 60s"
        )

    def test_the_warning_of_slowapi_is_not_repeated(self):
        # The handler's line above says the same and more.
        assert logging.getLogger("slowapi").getEffectiveLevel() == logging.ERROR
