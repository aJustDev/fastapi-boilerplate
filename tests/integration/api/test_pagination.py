"""Walking the pages of a list returns every row once, in order, for every sort field."""

import pytest
from httpx import AsyncClient

from app.items.schemas.item import ItemSortField
from tests.integration.api.helpers import signed_up

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

# Ties on purpose in category and priority: the id tiebreaker has to carry the paging.
ITEMS = [
    ("delta", "books", 2),
    ("alpha", "sports", 1),
    ("echo", "books", 1),
    ("bravo", "general", 2),
    ("golf", "sports", 2),
    ("charlie", "books", 1),
    ("foxtrot", "general", 1),
]


async def _seed(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    created = []
    for name, category, priority in ITEMS:
        response = await client.post(
            "/v1/items",
            json={"name": name, "category": category, "priority": priority},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        created.append(response.json())
    return created


@pytest.mark.parametrize("order_dir", ["asc", "desc"])
@pytest.mark.parametrize("order_by", list(ItemSortField))
async def test_cursor_pages_cover_every_row_once_in_order(
    api_client: AsyncClient, order_by: ItemSortField, order_dir: str
):
    headers = await signed_up(api_client, "alice")
    created = await _seed(api_client, headers)

    seen: list[dict] = []
    cursor: str | None = None
    for _ in range(len(ITEMS) + 1):  # a broken cursor must not loop forever
        params = {"limit": 3, "order_by": order_by.value, "order_dir": order_dir}
        if cursor:
            params["cursor"] = cursor
        response = await api_client.get("/v1/items/cursor", params=params, headers=headers)
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(page["items"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break

    assert sorted(i["id"] for i in seen) == sorted(i["id"] for i in created)
    keys = [(i[order_by.value], i["id"]) for i in seen]
    assert keys == sorted(keys, reverse=order_dir == "desc")


async def test_a_cursor_issued_for_another_order_is_rejected(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    await _seed(api_client, headers)
    by_name = await api_client.get(
        "/v1/items/cursor", params={"limit": 2, "order_by": "name"}, headers=headers
    )

    response = await api_client.get(
        "/v1/items/cursor",
        params={"limit": 2, "order_by": "priority", "cursor": by_name.json()["next_cursor"]},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"
