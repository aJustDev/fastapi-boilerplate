from unittest.mock import MagicMock

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from starlette.datastructures import URL

from app.core.exceptions import AuthenticationError, ConflictError, NotFoundError
from app.core.exceptions.handlers import (
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
        exc = NotFoundError("Item", 42)

        response = await domain_exception_handler(request, exc)

        assert response.status_code == 404
        assert b"Item not found" in response.body

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
        request = _make_request("POST", "/items")
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
