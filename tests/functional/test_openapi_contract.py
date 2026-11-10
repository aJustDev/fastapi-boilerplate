"""The OpenAPI document says what the API really answers, operation by operation.

A client generated from it has to know that a route can answer 401, 404 or 429 with the
error body; declaring the error schemas once and referencing them from no operation tells
it nothing.
"""

import pytest

from main import app

SCHEMA = app.openapi()
ERROR = "#/components/schemas/ErrorResponse"


def _operations() -> list[tuple[str, str, dict]]:
    return [
        (method.upper(), path, operation)
        for path, item in SCHEMA["paths"].items()
        for method, operation in item.items()
    ]


def _ids(operations: list[tuple[str, str, dict]]) -> list[str]:
    return [f"{method} {path}" for method, path, _ in operations]


ALL = _operations()
PROTECTED = [op for op in ALL if op[2].get("security")]
WITH_ID = [op for op in ALL if "{" in op[1]]


def _ref(operation: dict, status: str) -> str | None:
    content = operation["responses"].get(status, {}).get("content", {})
    return content.get("application/json", {}).get("schema", {}).get("$ref")


def test_scanner_sees_the_api():
    assert len(ALL) >= 12
    assert len(PROTECTED) >= 8
    assert len(WITH_ID) >= 3


@pytest.mark.parametrize(("method", "path", "operation"), PROTECTED, ids=_ids(PROTECTED))
def test_a_protected_operation_declares_401(method: str, path: str, operation: dict):
    assert _ref(operation, "401") == ERROR


@pytest.mark.parametrize(("method", "path", "operation"), WITH_ID, ids=_ids(WITH_ID))
def test_an_operation_on_a_resource_declares_404(method: str, path: str, operation: dict):
    assert _ref(operation, "404") == ERROR


@pytest.mark.parametrize(("method", "path", "operation"), ALL, ids=_ids(ALL))
def test_a_rate_limited_operation_declares_429(method: str, path: str, operation: dict):
    if "/health/" in path:
        pytest.skip("probes are exempt from rate limits")
    assert _ref(operation, "429") == ERROR
    assert "Retry-After" in operation["responses"]["429"]["headers"]


@pytest.mark.parametrize(("method", "path", "operation"), ALL, ids=_ids(ALL))
def test_every_operation_is_described(method: str, path: str, operation: dict):
    assert operation.get("description"), "add a docstring to the endpoint"


@pytest.mark.parametrize(("method", "path", "operation"), ALL, ids=_ids(ALL))
def test_every_success_response_with_a_body_has_a_schema(method: str, path: str, operation: dict):
    success = next(status for status in operation["responses"] if status.startswith("2"))
    if success == "204":
        return
    schema = operation["responses"][success]["content"]["application/json"]["schema"]
    assert schema, "declare a response_model"


def test_guards_and_conflicts_are_declared_where_they_happen():
    paths = SCHEMA["paths"]
    assert _ref(paths["/v1/items"]["post"], "403") == ERROR
    assert _ref(paths["/v1/auth/register"]["post"], "409") == ERROR
    assert _ref(paths["/v1/items/cursor"]["get"], "400") == ERROR
    assert "503" in paths["/v1/health/readiness"]["get"]["responses"]


def _request_schemas() -> list[str]:
    names = set()
    for _, _, operation in ALL:
        content = operation.get("requestBody", {}).get("content", {})
        ref = content.get("application/json", {}).get("schema", {}).get("$ref")
        if ref:
            names.add(ref.rsplit("/", 1)[1])
    return sorted(names)


@pytest.mark.parametrize("name", _request_schemas())
def test_every_field_a_client_sends_is_described(name: str):
    properties = SCHEMA["components"]["schemas"][name]["properties"]
    missing = [field for field, spec in properties.items() if not spec.get("description")]
    assert not missing, f"{name}: describe {missing}"
