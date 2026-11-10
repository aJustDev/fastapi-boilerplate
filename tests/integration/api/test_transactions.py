"""What a client is told about its write matches what the database kept."""

import pytest
from httpx import AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.integration.api.helpers import signed_up

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_a_write_is_visible_to_the_next_request(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")

    created = await api_client.post("/v1/items", json={"name": "kept"}, headers=headers)
    assert created.status_code == 201

    fetched = await api_client.get(f"/v1/items/{created.json()['id']}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "kept"


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
        created = await api_client.post("/v1/items", json={"name": "lost"}, headers=headers)

    assert not created.is_success, f"the API answered {created.status_code} for a lost write"
    listed = await api_client.get("/v1/items", headers=headers)
    assert listed.json()["total"] == 0


async def test_a_failed_request_stores_nothing(api_client: AsyncClient):
    headers = await signed_up(api_client, "alice")

    missing = await api_client.patch("/v1/items/999", json={"name": "x"}, headers=headers)

    assert missing.status_code == 404
    listed = await api_client.get("/v1/items", headers=headers)
    assert listed.json()["total"] == 0
