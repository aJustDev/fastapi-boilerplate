"""What a client is told about its write matches what the database kept."""

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events.bus import EventBus
from tests._workshops import workshop_body
from tests.integration.api.helpers import signed_up
from tests.integration.api.workshops import (
    create_workshop,
    enroll,
    events,
    get_workshop,
    published_workshop,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _drafts(client: AsyncClient, headers: dict[str, str]) -> list[dict]:
    response = await client.get("/v1/workshops", params={"status": "draft"}, headers=headers)
    items: list[dict] = response.json()["items"]
    return items


async def test_a_write_is_visible_to_the_next_request(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")

    created = await create_workshop(api_client, headers, title="kept")

    assert (await get_workshop(api_client, headers, created["id"]))["title"] == "kept"


async def test_a_failed_commit_is_not_reported_as_success(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    # The commit is part of the request: if it fails (connection lost at COMMIT, a
    # deferred constraint, a serialization failure) the client must not get a 2xx.
    headers = await signed_up(api_client, "alice")

    async def failing_commit(self: AsyncSession) -> None:
        await self.rollback()
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    with monkeypatch.context() as patched:
        patched.setattr(AsyncSession, "commit", failing_commit)
        created = await api_client.post("/v1/workshops", json=workshop_body(), headers=headers)

    assert not created.is_success, f"the API answered {created.status_code} for a lost write"
    assert await _drafts(api_client, headers) == []


async def test_a_failed_request_stores_nothing(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")

    missing = await api_client.patch(
        "/v1/workshops/999", json={"version": 1, "title": "x"}, headers=headers
    )

    assert missing.status_code == 404
    assert await _drafts(api_client, headers) == []


async def test_a_request_that_fails_halfway_keeps_none_of_its_writes(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    # Enrolling writes the enrollment, the seat count and the event. The event fails
    # last: the two writes before it must go with it.
    alice = await signed_up(api_client, "alice")
    bob = await signed_up(api_client, "bob")
    workshop = await published_workshop(api_client, alice)

    async def failing_publish(self: EventBus, *args: object, **kwargs: object) -> None:
        raise RuntimeError("outbox unavailable")

    with monkeypatch.context() as patched:
        patched.setattr(EventBus, "publish", failing_publish)
        failed = await enroll(api_client, bob, workshop["id"])

    assert failed.status_code == 500
    assert (await get_workshop(api_client, bob, workshop["id"]))["seats_taken"] == 0
    mine = await api_client.get("/v1/me/enrollments", headers=bob)
    assert mine.json()["total"] == 0
    assert await events() == []
