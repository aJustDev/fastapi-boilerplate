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


# ── Offset pagination ─────────────────────────────────────


async def _seed_many(client: AsyncClient, headers: dict[str, str], count: int) -> list[int]:
    # Few distinct values over many rows: almost every row ties with others on the sort
    # field, which is when an ORDER BY without a tiebreaker starts shuffling pages.
    ids = []
    for n in range(count):
        response = await client.post(
            "/v1/items",
            json={
                "name": f"item {n % 3}",
                "category": ("books", "sports")[n % 2],
                "priority": n % 2,
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return ids


@pytest.mark.parametrize("order_dir", ["asc", "desc"])
@pytest.mark.parametrize("order_by", list(ItemSortField))
async def test_offset_pages_cover_every_row_once_in_order(
    api_client: AsyncClient, order_by: ItemSortField, order_dir: str
):
    headers = await signed_up(api_client, "alice")
    created = await _seed_many(api_client, headers, 40)

    seen: list[dict] = []
    for page in range(1, 7):
        response = await api_client.get(
            "/v1/items",
            params={
                "page": page,
                "page_size": 7,
                "order_by": order_by.value,
                "order_dir": order_dir,
            },
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == len(created)
        seen.extend(response.json()["items"])

    assert sorted(i["id"] for i in seen) == sorted(created)
    keys = [(i[order_by.value], i["id"]) for i in seen]
    assert keys == sorted(keys, reverse=order_dir == "desc")


async def test_a_page_past_the_end_still_reports_the_total(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    await _seed(api_client, headers)

    response = await api_client.get("/v1/items", params={"page": 99}, headers=headers)

    assert response.json()["items"] == []
    assert response.json()["total"] == len(ITEMS)


async def test_the_text_filter_matches_its_characters_literally(api_client: AsyncClient):
    # % and _ are wildcards of LIKE. Sent by a client they are just characters.
    headers = await signed_up(api_client, "alice")
    await _seed(api_client, headers)
    await api_client.post("/v1/items", json={"name": "100%_done"}, headers=headers)

    async def names(pattern: str) -> list[str]:
        response = await api_client.get("/v1/items", params={"name": pattern}, headers=headers)
        return [i["name"] for i in response.json()["items"]]

    assert await names("%") == ["100%_done"]
    assert await names("_") == ["100%_done"]
    assert await names("0%_d") == ["100%_done"]
    assert await names("ALPH") == ["alpha"]  # still a case-insensitive "contains"
