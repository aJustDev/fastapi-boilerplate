"""Shape of the error responses, as the handlers in handlers.py build them.

The handlers build the body as a dict, not through these models, so nothing on its own
keeps both in sync: tests/functional/test_error_contract.py validates real responses
against them. `extra="forbid"` publishes `additionalProperties: false`, which turns the
schema into a contract instead of a minimum.
"""

from pydantic import BaseModel, ConfigDict


class ErrorResponse(BaseModel):
    """Every error of the API except the 422 of request validation."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"detail": "Workshop not found", "code": "not_found"}]},
    )

    detail: str
    code: str


class ValidationErrorResponse(BaseModel):
    """422: the request did not validate. Per-field messages go in `errors`."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "detail": "Validation error",
                    "code": "validation_error",
                    "errors": ["body.name: Field required"],
                }
            ]
        },
    )

    detail: str
    code: str
    errors: list[str]


def _error(description: str, code: str, detail: str) -> dict[str, object]:
    return {
        "model": ErrorResponse,
        "description": description,
        "content": {"application/json": {"example": {"detail": detail, "code": code}}},
    }


# What a route can answer besides its success, to declare where it applies:
# `APIRouter(responses={**UNAUTHENTICATED, **RATE_LIMITED})` for a whole router,
# `@router.get(..., responses={**NOT_FOUND})` for one route. The handlers produce these
# bodies; tests/functional/test_openapi_contract.py checks that the routes declare them.
Responses = dict[int | str, dict[str, object]]

BAD_REQUEST: Responses = {
    400: _error("The request is not acceptable", "invalid_cursor", "Invalid pagination cursor")
}
UNAUTHENTICATED: Responses = {
    401: _error(
        "Missing, invalid, expired or revoked credentials",
        "unauthenticated",
        "Invalid or expired token",
    )
}
FORBIDDEN: Responses = {
    403: _error(
        "The user lacks the permission of this route, or does not run the resource",
        "forbidden",
        "Permission 'workshops:create' required",
    )
}
NOT_FOUND: Responses = {
    404: _error(
        "No such resource, or not one the caller may see",
        "not_found",
        "Workshop not found (ID: 42)",
    )
}
CONFLICT: Responses = {
    409: _error(
        "Conflict with what is stored: a duplicate, or a state that does not allow the operation",
        "conflict",
        "Conflict on User: email taken",
    )
}
RATE_LIMITED: Responses = {
    429: {
        **_error("Rate limit of the route exceeded", "rate_limited", "Too many requests"),
        "headers": {
            "Retry-After": {
                "description": "Seconds until the limit opens again",
                "schema": {"type": "integer"},
            }
        },
    }
}


# Applied to every operation from main.py. The 500 holds for any route; the 422 is also
# declared on routes without parameters, a conscious over-declaration preferred to
# rewriting by hand what FastAPI generates.
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    422: {"model": ValidationErrorResponse, "description": "Invalid input"},
    500: {"model": ErrorResponse, "description": "Internal error"},
}
