"""What a request leaves behind besides its change: who made it and which request it was."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.auth.models.user import UserORM
from app.core.db import async_session_factory
from app.core.events.models import OutboxEventORM
from app.items.models.item import ItemORM
from tests.integration.api.helpers import register, signed_up

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _item(item_id: int) -> ItemORM:
    async with async_session_factory() as session:
        return (await session.execute(select(ItemORM).where(ItemORM.id == item_id))).scalar_one()


async def test_rows_record_who_created_and_who_changed_them(api_client: AsyncClient):
    alice = await signed_up(api_client, "alice")
    alice_id = (await api_client.get("/v1/auth/me", headers=alice)).json()["id"]
    created = (await api_client.post("/v1/items", json={"name": "x"}, headers=alice)).json()

    before = await _item(created["id"])
    await api_client.patch(f"/v1/items/{created['id']}", json={"name": "y"}, headers=alice)
    after = await _item(created["id"])

    assert before.created_by == str(alice_id)
    assert before.updated_by is None
    assert after.created_by == str(alice_id)
    assert after.updated_by == str(alice_id)


async def test_an_anonymous_request_records_nobody(api_client: AsyncClient):
    # The request before this one was authenticated: its user must not leak into this one.
    await signed_up(api_client, "alice")

    bob = await register(api_client, "bob")

    async with async_session_factory() as session:
        row = (await session.execute(select(UserORM).where(UserORM.id == bob["id"]))).scalar_one()
    assert row.created_by is None


async def test_an_event_carries_its_entity_and_its_request(api_client: AsyncClient):
    alice = await signed_up(api_client, "alice")

    created = await api_client.post(
        "/v1/items", json={"name": "x"}, headers={**alice, "X-Request-ID": "trace-42"}
    )

    async with async_session_factory() as session:
        event = (await session.execute(select(OutboxEventORM))).scalar_one()
    assert event.event_type == "item.created"
    assert event.aggregate_id == str(created.json()["id"])
    assert event.correlation_id == "trace-42"
