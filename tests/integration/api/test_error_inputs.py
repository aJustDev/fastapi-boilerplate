"""Malformed input is a 4xx with the error contract, never a 500.

Against a real database on purpose: most of these used to pass validation and fail inside
PostgreSQL or the driver, which a mocked session cannot show.
"""

import base64
import json

import pytest
from httpx import AsyncClient

from tests._workshops import workshop_body
from tests.integration.api.helpers import PASSWORD, signed_up
from tests.integration.api.workshops import create_workshop

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

NUL = "a\x00b"
BEYOND_BIGINT = 2**63
BEYOND_INT = 2**31
# A valid ISO date with no UTC equivalent: year 1 at +14:00 is year 0 in UTC.
BEFORE_TIME = "0001-01-01T00:00:00+14:00"


def _cursor(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode()


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": NUL},
        {"title": ""},
        {"title": "   "},
        {"title": "x" * 201},
        {"description": NUL},
        {"description": "x" * 10_001},
        {"capacity": 0},
        {"capacity": BEYOND_INT},
        {"starts_at": "2030-05-04T10:00:00"},
        {"starts_at": BEFORE_TIME},
        {"ends_at": "9999-12-31T23:59:59-12:00"},
    ],
    ids=[
        "nul-in-title",
        "empty-title",
        "blank-title",
        "title-too-long",
        "nul-in-description",
        "description-too-long",
        "no-seats",
        "capacity-above-int4",
        "start-without-offset",
        "start-before-year-1-in-utc",
        "end-after-year-9999-in-utc",
    ],
)
async def test_create_rejects_what_the_columns_cannot_hold(api_client: AsyncClient, overrides):
    headers = await signed_up(api_client, "alice")

    response = await api_client.post(
        "/v1/workshops", json=workshop_body(**overrides), headers=headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("field", ["title", "starts_at", "ends_at", "capacity"])
async def test_patch_rejects_null_for_a_column_that_is_not_nullable(
    api_client: AsyncClient, field: str
):
    headers = await signed_up(api_client, "alice")
    workshop = await create_workshop(api_client, headers)

    response = await api_client.patch(
        f"/v1/workshops/{workshop['id']}", json={"version": 1, field: None}, headers=headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


async def test_patch_may_clear_a_nullable_column(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    workshop = await create_workshop(api_client, headers, description="to clear")

    response = await api_client.patch(
        f"/v1/workshops/{workshop['id']}",
        json={"version": 1, "description": None},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


@pytest.mark.parametrize("version", [BEYOND_INT, -BEYOND_INT - 1, "one", None])
async def test_patch_rejects_a_version_that_is_not_one(api_client: AsyncClient, version):
    headers = await signed_up(api_client, "alice")
    workshop = await create_workshop(api_client, headers)

    response = await api_client.patch(
        f"/v1/workshops/{workshop['id']}", json={"version": version}, headers=headers
    )

    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "url",
    [
        f"/v1/workshops/{BEYOND_BIGINT}",
        "/v1/workshops/0",
        f"/v1/workshops/1/enrollments/{BEYOND_BIGINT}/attendance",
        "/v1/me/enrollments?page=9999999999999999999",
        "/v1/me/enrollments?page_size=101",
        "/v1/me/enrollments?status=enrolled",
        "/v1/workshops?q=a%00b",
        f"/v1/workshops?q={'x' * 201}",
        "/v1/workshops?limit=0",
        f"/v1/workshops?cursor={'x' * 2000}",
        "/v1/workshops?status=open",
        "/v1/workshops?order_by=title",
        "/v1/workshops?starts_after=tomorrow",
        "/v1/workshops?starts_after=2030-05-04T10:00:00",
        f"/v1/workshops?starts_after={BEFORE_TIME.replace('+', '%2B')}",
    ],
    ids=[
        "id-above-bigint",
        "id-zero",
        "child-id-above-bigint",
        "page-above-bigint",
        "page-size-above-limit",
        "enrollment-status-unknown",
        "nul-in-filter",
        "filter-too-long",
        "limit-zero",
        "cursor-too-long",
        "status-unknown",
        "sort-field-unknown",
        "date-that-is-not-one",
        "date-without-offset",
        "date-before-year-1-in-utc",
    ],
)
async def test_path_and_query_values_are_bounded(api_client: AsyncClient, url: str):
    headers = await signed_up(api_client, "alice")

    method = "POST" if url.endswith("/attendance") else "GET"
    response = await api_client.request(method, url, json={"attended": True}, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    "cursor",
    [
        "abc",
        "!!!",
        _cursor("not json"),
        _cursor("[1]"),
        _cursor("{}"),
        _cursor('{"id": "x"}'),
        _cursor('{"id": 1}'),
        _cursor('{"id": 1, "starts_at": "soon"}'),
        _cursor('{"id": 1, "starts_at": {"$gt": ""}}'),
    ],
    ids=[
        "bad-base64",
        "not-base64",
        "not-json",
        "not-an-object",
        "no-id",
        "id-of-wrong-type",
        "no-sort-value",
        "sort-value-that-is-not-a-date",
        "sort-value-that-is-an-object",
    ],
)
async def test_a_cursor_the_api_did_not_issue_is_rejected(api_client: AsyncClient, cursor: str):
    headers = await signed_up(api_client, "alice")

    response = await api_client.get("/v1/workshops", params={"cursor": cursor}, headers=headers)

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "invalid_cursor"


async def test_a_forged_cursor_with_an_impossible_date_is_not_a_500(api_client: AsyncClient):
    # Well formed, so it reaches the query; the driver refuses the value.
    headers = await signed_up(api_client, "alice")
    cursor = _cursor(json.dumps({"id": 1, "starts_at": BEFORE_TIME}))

    response = await api_client.get("/v1/workshops", params={"cursor": cursor}, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "invalid_input"


@pytest.mark.parametrize(
    "overrides",
    [
        {"username": NUL},
        {"username": ""},
        {"username": "  "},
        {"username": "ab"},
        {"username": "x" * 51},
        {"username": "someone@example.com"},
        {"username": "with space"},
        {"full_name": NUL},
        {"full_name": "x" * 201},
        {"password": "short"},
        {"password": "x" * 129},
        {"password": "nul\x00inside"},
    ],
    ids=[
        "nul-in-username",
        "empty-username",
        "blank-username",
        "username-too-short",
        "username-too-long",
        "username-shaped-like-an-email",
        "username-with-space",
        "nul-in-full-name",
        "full-name-too-long",
        "password-too-short",
        "password-too-long",
        "nul-in-password",
    ],
)
async def test_register_rejects_malformed_fields(api_client: AsyncClient, overrides: dict):
    body = {"email": "bob@example.com", "username": "bob", "password": PASSWORD} | overrides

    response = await api_client.post("/v1/auth/register", json=body)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    "form",
    [
        {"username": NUL, "password": PASSWORD},
        {"username": "alice", "password": NUL},
        {"username": "x" * 400, "password": PASSWORD},
        {"username": "alice", "password": "x" * 5000},
    ],
    ids=["nul-in-username", "nul-in-password", "username-too-long", "password-too-long"],
)
async def test_login_with_impossible_credentials_is_a_plain_401(api_client: AsyncClient, form):
    await signed_up(api_client, "alice")

    response = await api_client.post("/v1/auth/login", data=form)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "unauthenticated"


async def test_a_request_id_that_is_not_text_does_not_break_the_request(api_client: AsyncClient):
    response = await api_client.get("/v1/health/liveness", headers={"X-Request-ID": b"\xff\xfe"})

    assert response.status_code == 200
    assert len(response.headers["X-Request-ID"]) == 32
