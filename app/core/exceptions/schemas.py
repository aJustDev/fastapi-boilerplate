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
        json_schema_extra={"examples": [{"detail": "Item not found", "code": "not_found"}]},
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


# Applied to every operation from main.py. The 500 holds for any route; the 422 is also
# declared on routes without parameters, a conscious over-declaration preferred to
# rewriting by hand what FastAPI generates.
ERROR_RESPONSES: dict[int | str, dict[str, object]] = {
    422: {"model": ValidationErrorResponse, "description": "Invalid input"},
    500: {"model": ErrorResponse, "description": "Internal error"},
}
