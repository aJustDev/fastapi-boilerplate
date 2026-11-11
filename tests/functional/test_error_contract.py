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
from sqlalchemy.exc import DBAPIError, IntegrityError
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.exceptions import NotFoundError
from app.core.exceptions.handlers import (
    database_error_handler,
    domain_exception_handler,
    http_exception_handler,
    integrity_error_handler,
    rate_limit_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions.schemas import ErrorResponse, ValidationErrorResponse
from main import app
from tests._workshops import workshop_body


def _request() -> Request:
    return Request(
        {"type": "http", "method": "GET", "path": "/v1/x", "headers": [], "query_string": b""}
    )


def _body(response: JSONResponse) -> dict:
    return json.loads(bytes(response.body))


class _DriverError(Exception):
    """What SQLAlchemy's asyncpg dialect puts in `DBAPIError.orig`: it exposes `sqlstate`."""

    def __init__(self, sqlstate: str, message: str = "rejected") -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


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
        response = await domain_exception_handler(_request(), NotFoundError("Workshop", 1))
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

    async def test_integrity_error_for_a_missing_value_is_a_422(self):
        # NOT NULL and CHECK violations are input the schema should have refused, not a
        # conflict with stored data.
        for sqlstate in ("23502", "23514"):
            exc = IntegrityError("INSERT ...", {}, _DriverError(sqlstate))
            response = await integrity_error_handler(_request(), exc)
            assert response.status_code == 422
            assert ValidationErrorResponse.model_validate(_body(response)).code == "invalid_input"

    async def test_data_error(self):
        exc = DBAPIError("INSERT ...", {}, _DriverError("22021"))
        response = await database_error_handler(_request(), exc)
        assert response.status_code == 422
        assert ValidationErrorResponse.model_validate(_body(response)).code == "invalid_input"

    @pytest.mark.parametrize("sqlstate", ["55P03", "40P01", "40001"])
    async def test_a_transaction_that_lost_to_another_is_a_503(self, sqlstate: str):
        # Lock timeout, deadlock, serialization failure: nothing was stored and the same
        # request is expected to work if sent again.
        exc = DBAPIError("SELECT ... FOR UPDATE", {}, _DriverError(sqlstate))
        response = await database_error_handler(_request(), exc)
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "1"
        assert ErrorResponse.model_validate(_body(response)).code == "busy"

    async def test_any_other_database_error_is_not_the_clients_fault(self):
        # The handler declines it: raised again, it ends as a 500 in the middleware.
        exc = DBAPIError("SELECT ...", {}, _DriverError("57014"))  # query_canceled
        with pytest.raises(DBAPIError):
            await database_error_handler(_request(), exc)

    async def test_database_messages_are_not_logged(self, caplog: pytest.LogCaptureFixture):
        # PostgreSQL quotes the offending values in its message; the log keeps the class,
        # the SQLSTATE and the constraint only.
        orig = _DriverError("23505", "duplicate key\nDETAIL: Key (lower(email))=(a@b.c) exists.")
        with caplog.at_level("WARNING"):
            await integrity_error_handler(_request(), IntegrityError("INSERT ...", {}, orig))
        assert "a@b.c" not in caplog.text
        assert "sqlstate=23505" in caplog.text

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
        "database_error_handler",
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
            response = await client.post("/v1/workshops", json={}, headers=auth_headers)
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
                "app.workshops.repos.workshop.WorkshopRepo.create",
                side_effect=IntegrityError("INSERT", {}, Exception("duplicate")),
            ),
        ):
            response = await client.post(
                "/v1/workshops", json=workshop_body(), headers=auth_headers
            )
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
            patch(
                "app.workshops.repos.workshop.WorkshopRepo.get_by_id",
                side_effect=RuntimeError("boom"),
            ),
            caplog.at_level("ERROR"),
        ):
            response = await client.get(
                "/v1/workshops/1",
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
        assert len(errors) == 1, "one log record per unhandled error"
        assert errors[0].exc_info is not None
        # The message is one line; the traceback travels apart (the `exception` field).
        assert errors[0].getMessage().startswith("Unhandled RuntimeError: boom (app/")
        assert errors[0].getMessage().endswith(", GET /v1/workshops/1)")


@pytest.mark.parametrize("status", ["422", "500"])
def test_openapi_declares_the_error_schemas(status: str):
    schema = app.openapi()
    operation = schema["paths"]["/v1/workshops"]["post"]
    ref = operation["responses"][status]["content"]["application/json"]["schema"]["$ref"]
    expected = "ValidationErrorResponse" if status == "422" else "ErrorResponse"
    assert ref.endswith(f"/{expected}")
