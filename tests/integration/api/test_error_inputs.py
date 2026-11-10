"""Malformed input is a 4xx with the error contract, never a 500.

Against a real database on purpose: most of these used to pass validation and fail inside
PostgreSQL or the driver, which a mocked session cannot show.
"""

import base64

import pytest
from httpx import AsyncClient

from tests.integration.api.helpers import PASSWORD, signed_up

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

NUL = "a\x00b"
BEYOND_BIGINT = 2**63
BEYOND_INT = 2**31


def _cursor(raw: str) -> str:
    return base64.urlsafe_b64encode(raw.encode()).decode()


@pytest.mark.parametrize(
    "body",
    [
        {"name": NUL},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 201},
        {"name": "ok", "description": NUL},
        {"name": "ok", "description": "x" * 10_001},
        {"name": "ok", "priority": BEYOND_INT},
        {"name": "ok", "priority": -BEYOND_INT - 1},
    ],
    ids=[
        "nul-in-name",
        "empty-name",
        "blank-name",
        "name-too-long",
        "nul-in-description",
        "description-too-long",
        "priority-above-int4",
        "priority-below-int4",
    ],
)
async def test_create_item_rejects_what_the_column_cannot_hold(api_client: AsyncClient, body):
    headers = await signed_up(api_client, "alice")

    response = await api_client.post("/v1/items", json=body, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("field", ["name", "category", "priority", "is_active"])
async def test_patch_rejects_null_for_a_column_that_is_not_nullable(
    api_client: AsyncClient, field: str
):
    headers = await signed_up(api_client, "alice")
    item = (await api_client.post("/v1/items", json={"name": "ok"}, headers=headers)).json()

    response = await api_client.patch(
        f"/v1/items/{item['id']}", json={field: None}, headers=headers
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


async def test_patch_may_clear_a_nullable_column(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    item = (
        await api_client.post(
            "/v1/items", json={"name": "ok", "description": "to clear"}, headers=headers
        )
    ).json()

    response = await api_client.patch(
        f"/v1/items/{item['id']}", json={"description": None}, headers=headers
    )

    assert response.status_code == 200
    assert response.json()["description"] is None


@pytest.mark.parametrize(
    "url",
    [
        f"/v1/items/{BEYOND_BIGINT}",
        "/v1/items/0",
        "/v1/items?page=9999999999999999999",
        "/v1/items?page_size=101",
        "/v1/items?name=a%00b",
        f"/v1/items?name={'x' * 201}",
        "/v1/items/cursor?limit=0",
        f"/v1/items/cursor?cursor={'x' * 2000}",
    ],
    ids=[
        "id-above-bigint",
        "id-zero",
        "page-above-bigint",
        "page-size-above-limit",
        "nul-in-filter",
        "filter-too-long",
        "limit-zero",
        "cursor-too-long",
    ],
)
async def test_path_and_query_values_are_bounded(api_client: AsyncClient, url: str):
    headers = await signed_up(api_client, "alice")

    response = await api_client.get(url, headers=headers)

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize(
    "cursor",
    ["abc", "!!!", _cursor("not json"), _cursor("[1]"), _cursor("{}"), _cursor('{"id": "x"}')],
    ids=["bad-base64", "not-base64", "not-json", "not-an-object", "no-id", "id-of-wrong-type"],
)
async def test_a_cursor_the_api_did_not_issue_is_rejected(api_client: AsyncClient, cursor: str):
    headers = await signed_up(api_client, "alice")

    response = await api_client.get("/v1/items/cursor", params={"cursor": cursor}, headers=headers)

    assert response.status_code == 400, response.text
    assert response.json()["code"] == "invalid_cursor"


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
