"""Steps on workshops shared by the API tests. They go through HTTP like any client;
the two that do not (`begin`, `events`) say why."""

from datetime import timedelta
from typing import Any

from httpx import AsyncClient, Response
from sqlalchemy import func, select, update

from app.core.db import async_session_factory
from app.core.events.models import OutboxEventORM
from app.workshops.models.workshop import WorkshopORM
from tests._workshops import workshop_body


async def create_workshop(client: AsyncClient, headers: dict[str, str], **overrides: Any) -> dict:
    """A draft organized by the owner of `headers`."""
    response = await client.post("/v1/workshops", json=workshop_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    body: dict = response.json()
    return body


async def published_workshop(
    client: AsyncClient, headers: dict[str, str], **overrides: Any
) -> dict:
    draft = await create_workshop(client, headers, **overrides)
    response = await client.post(f"/v1/workshops/{draft['id']}/publish", headers=headers)
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


async def enroll(client: AsyncClient, headers: dict[str, str], workshop_id: int) -> Response:
    return await client.post(f"/v1/workshops/{workshop_id}/enrollments", headers=headers)


async def get_workshop(client: AsyncClient, headers: dict[str, str], workshop_id: int) -> dict:
    response = await client.get(f"/v1/workshops/{workshop_id}", headers=headers)
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


async def begin(workshop_id: int) -> None:
    """Make the workshop start an hour ago. Time passing is the one thing a client
    cannot do, so this writes to the database."""
    async with async_session_factory() as session:
        await session.execute(
            update(WorkshopORM)
            .where(WorkshopORM.id == workshop_id)
            .values(starts_at=func.now() - timedelta(hours=1))
        )
        await session.commit()


async def events(event_type: str | None = None) -> list[OutboxEventORM]:
    """The events the requests left in the outbox. No route exposes them.

    Oldest transaction first; events of one transaction share its timestamp and come in
    no particular order.
    """
    stmt = select(OutboxEventORM).order_by(OutboxEventORM.created_at, OutboxEventORM.id)
    if event_type is not None:
        stmt = stmt.where(OutboxEventORM.event_type == event_type)
    async with async_session_factory() as session:
        return list((await session.execute(stmt)).scalars())
