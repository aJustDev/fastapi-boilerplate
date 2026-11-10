"""Walking the pages of a list through HTTP returns every row once, in order.

The repository is tested with every sort field in tests/integration/core/test_base_repo.py.
Here the cursor travels the way a client carries it: as text in a URL, with a date in it.
"""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.workshops.schemas.workshop import WorkshopSortField
from tests.integration.api.helpers import signed_up
from tests.integration.api.workshops import create_workshop, enroll, published_workshop

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

DAY_ONE = datetime(2031, 3, 1, 9, tzinfo=UTC)
# Ties on purpose: three workshops start at the same instant, two at another. The id
# tiebreaker has to carry the paging across them.
STARTS = [2, 0, 1, 0, 2, 0, 1]


async def _seed(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    created = []
    for n, day in enumerate(STARTS):
        starts_at = DAY_ONE + timedelta(days=day)
        created.append(
            await create_workshop(
                client,
                headers,
                title=f"workshop {n}",
                starts_at=starts_at.isoformat(),
                ends_at=(starts_at + timedelta(hours=1)).isoformat(),
            )
        )
    return created


@pytest.mark.parametrize("order_dir", ["asc", "desc"])
@pytest.mark.parametrize("order_by", list(WorkshopSortField))
async def test_cursor_pages_cover_every_row_once_in_order(
    api_client: AsyncClient, order_by: WorkshopSortField, order_dir: str
):
    headers = await signed_up(api_client, "alice")
    created = await _seed(api_client, headers)

    seen: list[dict] = []
    cursor: str | None = None
    for _ in range(len(created) + 1):  # a broken cursor must not loop forever
        params = {"limit": 3, "order_by": order_by.value, "order_dir": order_dir}
        if cursor:
            params["cursor"] = cursor
        response = await api_client.get("/v1/workshops", params=params, headers=headers)
        assert response.status_code == 200, response.text
        page = response.json()
        seen.extend(page["items"])
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break

    assert sorted(w["id"] for w in seen) == sorted(w["id"] for w in created)
    keys = [(w[order_by.value], w["id"]) for w in seen]
    assert keys == sorted(keys, reverse=order_dir == "desc")


async def test_the_default_order_is_by_start(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    await _seed(api_client, headers)

    response = await api_client.get("/v1/workshops", headers=headers)

    starts = [w["starts_at"] for w in response.json()["items"]]
    assert starts == sorted(starts)


async def test_a_cursor_issued_for_another_order_is_rejected(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    await _seed(api_client, headers)
    by_start = await api_client.get(
        "/v1/workshops", params={"limit": 2, "order_by": "starts_at"}, headers=headers
    )

    response = await api_client.get(
        "/v1/workshops",
        params={"limit": 2, "order_by": "created_at", "cursor": by_start.json()["next_cursor"]},
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "invalid_cursor"


async def test_filters_narrow_the_list(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")
    await _seed(api_client, headers)
    await published_workshop(api_client, headers, title="100%_done")

    async def titles(**params: str) -> list[str]:
        response = await api_client.get("/v1/workshops", params=params, headers=headers)
        assert response.status_code == 200, response.text
        return [w["title"] for w in response.json()["items"]]

    assert await titles(status="published") == ["100%_done"]
    assert len(await titles(status="draft")) == len(STARTS)
    after_day_one = (DAY_ONE + timedelta(days=1)).isoformat()
    assert sorted(await titles(starts_after=after_day_one, status="draft")) == [
        "workshop 0",
        "workshop 2",
        "workshop 4",
        "workshop 6",
    ]
    # % and _ are wildcards of LIKE. Sent by a client they are just characters.
    assert await titles(q="%") == ["100%_done"]
    assert await titles(q="_") == ["100%_done"]
    assert await titles(q="SHOP 3") == ["workshop 3"]  # a case-insensitive "contains"


# ── Offset pagination ─────────────────────────────────────


async def test_offset_pages_cover_every_row_once_newest_first(api_client: AsyncClient):
    alice = await signed_up(api_client, "alice")
    bob = await signed_up(api_client, "bob")
    enrolled = []
    for _ in range(9):
        workshop = await published_workshop(api_client, alice)
        enrolled.append((await enroll(api_client, bob, workshop["id"])).json()["id"])

    seen: list[dict] = []
    for page in (1, 2, 3):
        response = await api_client.get(
            "/v1/me/enrollments", params={"page": page, "page_size": 4}, headers=bob
        )
        assert response.status_code == 200, response.text
        assert response.json()["total"] == 9
        seen.extend(response.json()["items"])

    assert [e["id"] for e in seen] == sorted(enrolled, reverse=True)
    assert {e["workshop"]["id"] for e in seen} == {e["workshop_id"] for e in seen}


async def test_a_page_past_the_end_still_reports_the_total(api_client: AsyncClient):
    alice = await signed_up(api_client, "alice")
    workshop = await published_workshop(api_client, alice)
    await enroll(api_client, alice, workshop["id"])

    response = await api_client.get("/v1/me/enrollments", params={"page": 99}, headers=alice)

    assert response.json()["items"] == []
    assert response.json()["total"] == 1
