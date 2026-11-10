from unittest.mock import MagicMock, patch

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import URL

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.exceptions.handlers import (
    _format_log,
    domain_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)


def _make_request(method: str = "GET", path: str = "/test") -> MagicMock:
    request = MagicMock(spec=Request)
    request.method = method
    request.url = MagicMock(spec=URL)
    request.url.path = path
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


class TestLogColors:
    def _ctx(self) -> dict:
        return {
            "exc_name": "NotFoundError",
            "message": "Order not found",
            "filename": "app/x.py",
            "lineno": 1,
            "func": "f",
            "method": "GET",
            "path": "/v1/orders/1",
            "status_code": 404,
        }

    def test_no_ansi_codes_when_logging_json(self):
        # The message is built before the formatter runs, so JSON logs would carry
        # the escape codes inside the `message` field.
        with patch("app.core.exceptions.handlers.ansi_enabled", return_value=False):
            assert "\033" not in _format_log(self._ctx())

    def test_ansi_codes_when_console_supports_color(self):
        with patch("app.core.exceptions.handlers.ansi_enabled", return_value=True):
            assert "\033" in _format_log(self._ctx())
