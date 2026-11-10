"""What a request leaves behind besides its change: who made it and which request it was."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.auth.models.user import UserORM
from app.core.db import async_session_factory
from app.workshops.models.workshop import WorkshopORM
from tests.integration.api.helpers import register, signed_up
from tests.integration.api.workshops import create_workshop, events, published_workshop

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _row(workshop_id: int) -> WorkshopORM:
    async with async_session_factory() as session:
        stmt = select(WorkshopORM).where(WorkshopORM.id == workshop_id)
        return (await session.execute(stmt)).scalar_one()


async def _user_id(client: AsyncClient, headers: dict[str, str]) -> int:
    user_id: int = (await client.get("/v1/auth/me", headers=headers)).json()["id"]
    return user_id


async def test_rows_record_who_created_and_who_changed_them(api_client: AsyncClient):
    alice = await signed_up(api_client, "alice")
    alice_id = await _user_id(api_client, alice)
    created = await create_workshop(api_client, alice)
    before = await _row(created["id"])

    await api_client.patch(
        f"/v1/workshops/{created['id']}", json={"version": 1, "title": "y"}, headers=alice
    )
    after = await _row(created["id"])

    assert before.created_by == str(alice_id)
    assert before.updated_by is None
    assert after.created_by == str(alice_id)
    assert after.updated_by == str(alice_id)
    assert after.updated_at is not None


async def test_an_anonymous_request_records_nobody(api_client: AsyncClient):
    # The request before this one was authenticated: its user must not leak into this one.
    await signed_up(api_client, "alice")
    bob = await register(api_client, "bob")

    async with async_session_factory() as session:
        row = (await session.execute(select(UserORM).where(UserORM.id == bob["id"]))).scalar_one()

    assert row.created_by is None


async def test_an_event_carries_its_entity_and_its_request(api_client: AsyncClient):
    alice = await signed_up(api_client, "alice")
    workshop = await published_workshop(api_client, alice)

    enrolled = await api_client.post(
        f"/v1/workshops/{workshop['id']}/enrollments",
        headers={**alice, "X-Request-ID": "trace-42"},
    )

    (event,) = await events()
    assert event.event_type == "enrollment.confirmed"
    assert event.aggregate_id == str(enrolled.json()["id"])
    assert event.correlation_id == "trace-42"
    assert event.payload["attendee_id"] == await _user_id(api_client, alice)
