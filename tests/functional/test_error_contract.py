"""The error bodies the API sends match the schemas it publishes.

app/core/exceptions/schemas.py declares the shape in OpenAPI, but the handlers build the
body by hand. Two halves, because neither is enough alone:
- every registered handler, called directly: exhaustive and cheap, and it covers the
  ones that are hard to trigger over HTTP;
- real requests: a correct handler is useless if it is not wired or something below
  rewrites the body.
"""

import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from httpx import AsyncClient
from limits import parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.exceptions import NotFoundError
from app.core.exceptions.handlers import (
    domain_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    rate_limit_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions.schemas import ErrorResponse, ValidationErrorResponse
from main import app


def _request() -> Request:
    return Request(
        {"type": "http", "method": "GET", "path": "/v1/x", "headers": [], "query_string": b""}
    )


def _body(response: JSONResponse) -> dict:
    return json.loads(bytes(response.body))


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


class TestEveryHandler:
    async def test_domain_error(self):
        response = await domain_exception_handler(_request(), NotFoundError("Item", 1))
        assert ErrorResponse.model_validate(_body(response)).code == "not_found"

    async def test_http_exception(self):
        response = await http_exception_handler(_request(), HTTPException(status_code=405))
        assert ErrorResponse.model_validate(_body(response)).code == "method_not_allowed"

    async def test_validation(self):
        exc = RequestValidationError(
            [{"loc": ("body", "name"), "msg": "Field required", "type": "missing"}]
        )
        body = ValidationErrorResponse.model_validate(
            _body(await validation_exception_handler(_request(), exc))
        )
        assert body.errors == ["body.name: Field required"]

    async def test_rate_limit(self):
        response = await rate_limit_exception_handler(_request(), RateLimitExceeded(_limit()))
        assert ErrorResponse.model_validate(_body(response)).code == "rate_limited"
        # Without slowapi's request state: the whole window of the limit, in seconds.
        assert response.headers["Retry-After"] == "60"

    async def test_integrity_error(self):
        exc = IntegrityError("INSERT ...", {}, Exception("duplicate key"))
        response = await integrity_error_handler(_request(), exc)
        assert response.status_code == 409
        assert ErrorResponse.model_validate(_body(response)).code == "integrity_conflict"

    async def test_unhandled(self):
        response = await unhandled_exception_handler(_request(), RuntimeError("boom"))
        body = ErrorResponse.model_validate(_body(response))
        assert body.code == "internal_error"
        assert "boom" not in body.detail, "a 500 must not leak the internal message"


def test_every_registered_handler_is_checked():
    # Canary: a new handler with a shape of its own must not slip past this file.
    registered = {h.__name__ for h in app.exception_handlers.values()} - {
        # FastAPI's own; it closes the socket with a code, there is no JSON body.
        "websocket_request_validation_exception_handler",
    }
    checked = {
        "domain_exception_handler",
        "http_exception_handler",
        "validation_exception_handler",
        "rate_limit_exception_handler",
        "integrity_error_handler",
        "unhandled_exception_handler",
    }
    assert registered == checked


class TestRealRequests:
    async def test_unknown_route(self, client: AsyncClient):
        response = await client.get("/v1/does-not-exist")
        assert response.status_code == 404
        assert ErrorResponse.model_validate(response.json()).code == "not_found"

    async def test_wrong_method(self, client: AsyncClient):
        response = await client.put("/v1/health/liveness")
        assert response.status_code == 405
        assert ErrorResponse.model_validate(response.json()).code == "method_not_allowed"

    async def test_missing_credentials(self, client: AsyncClient):
        response = await client.get("/v1/auth/me")
        assert response.status_code == 401
        assert ErrorResponse.model_validate(response.json()).code == "unauthenticated"

    async def test_invalid_body(self, client: AsyncClient, auth_headers, fake_user):
        with (
            patch("app.auth.repos.revoked_token.RevokedTokenRepo.is_revoked", return_value=False),
            patch("app.auth.repos.user.UserRepo.get_by_id", return_value=fake_user),
        ):
            response = await client.post("/v1/items", json={}, headers=auth_headers)
        assert response.status_code == 422
        assert ValidationErrorResponse.model_validate(response.json()).errors

    async def test_duplicate_reaching_the_database(
        self, client: AsyncClient, auth_headers, fake_user
    ):
        # A race between the service check and the INSERT ends as 409, not 500.
        with (
            patch("app.auth.repos.revoked_token.RevokedTokenRepo.is_revoked", return_value=False),
            patch("app.auth.repos.user.UserRepo.get_by_id", return_value=fake_user),
            patch(
                "app.items.repos.item.ItemRepo.create",
                side_effect=IntegrityError("INSERT", {}, Exception("duplicate")),
            ),
        ):
            response = await client.post("/v1/items", json={"name": "x"}, headers=auth_headers)
        assert response.status_code == 409
        assert ErrorResponse.model_validate(response.json()).code == "integrity_conflict"

    async def test_unhandled_error_is_a_500_like_any_other_response(
        self, client: AsyncClient, auth_headers, fake_user, caplog: pytest.LogCaptureFixture
    ):
        # The 500 is produced inside the middleware stack: a browser can read it (CORS),
        # it carries the hardening headers, and its request id is in the response and in
        # the one log line of the error.
        with (
            patch("app.auth.repos.revoked_token.RevokedTokenRepo.is_revoked", return_value=False),
            patch("app.auth.repos.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.items.repos.item.ItemRepo.get_by_id", side_effect=RuntimeError("boom")),
            caplog.at_level("ERROR"),
        ):
            response = await client.get(
                "/v1/items/1",
                headers={
                    **auth_headers,
                    "Origin": "http://localhost:3000",
                    "X-Request-ID": "trace-123",
                },
            )

        assert response.status_code == 500
        body = ErrorResponse.model_validate(response.json())
        assert body.code == "internal_error"
        assert "boom" not in response.text
        assert response.headers["X-Request-ID"] == "trace-123"
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(errors) == 1, "one log line per unhandled error"
        assert errors[0].exc_info is not None


@pytest.mark.parametrize("status", ["422", "500"])
def test_openapi_declares_the_error_schemas(status: str):
    schema = app.openapi()
    operation = schema["paths"]["/v1/items"]["post"]
    ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
    expected = "ValidationErrorResponse" if status == "422" else "ErrorResponse"
    assert ref.endswith(f"/{expected}")
