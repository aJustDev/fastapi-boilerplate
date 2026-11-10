"""The operations CLI against a real database."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import cli
from app.core.db import async_session_factory
from app.core.events.bus import EventBus
from app.core.events.models import OutboxEventORM
from tests.integration.api.helpers import bearer, register

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

PASSWORD = "an-admin-password"  # noqa: S105 -- test credential


async def _roles(client: AsyncClient, username: str, password: str) -> list[str]:
    tokens = await client.post("/v1/auth/login", data={"username": username, "password": password})
    assert tokens.status_code == 200, tokens.text
    me = await client.get("/v1/auth/me", headers=bearer(tokens.json()["access_token"]))
    return [role["name"] for role in me.json()["roles"]]


class TestCreateAdmin:
    async def test_creates_an_account_that_can_log_in_as_administrator(
        self, api_client: AsyncClient
    ):
        message = await cli.create_admin("root@example.com", "root", PASSWORD)

        assert "created" in message
        assert await _roles(api_client, "root", PASSWORD) == ["admin"]

    async def test_promotes_an_existing_account_and_keeps_its_password(
        self, api_client: AsyncClient
    ):
        await register(api_client, "alice")

        message = await cli.create_admin("alice@example.com", "ignored", None)

        assert "now an administrator" in message
        assert sorted(await _roles(api_client, "alice", "correct-horse-battery")) == [
            "admin",
            "user",
        ]

    async def test_running_it_twice_changes_nothing(self, api_client: AsyncClient):
        await cli.create_admin("root@example.com", "root", PASSWORD)

        message = await cli.create_admin("root@example.com", "root", PASSWORD)

        assert "already" in message

    async def test_a_new_account_follows_the_registration_rules(self, app_database):
        with pytest.raises(ValueError, match="password"):
            await cli.create_admin("root@example.com", "root", "short")

    async def test_a_new_account_needs_a_password(self, app_database):
        with pytest.raises(SystemExit, match="password"):
            await cli.create_admin("root@example.com", "root", None)


class TestOutboxCommands:
    @staticmethod
    async def _publish_failed() -> uuid.UUID:
        async with async_session_factory() as session:
            event = await EventBus(session).publish("test.cli", {"n": 1})
            event.status, event.retry_count, event.last_error = "FAILED", 12, "boom"
            await session.commit()
            return event.id

    async def test_replay_puts_failed_events_back_in_the_queue(self, app_database):
        event_id = await self._publish_failed()

        await cli.main_async(["outbox", "replay"])

        async with async_session_factory() as session:
            event = (
                await session.execute(select(OutboxEventORM).where(OutboxEventORM.id == event_id))
            ).scalar_one()
        assert (event.status, event.retry_count, event.last_error) == ("PENDING", 0, None)

    async def test_replay_of_one_id_leaves_the_others(self, app_database):
        first, second = await self._publish_failed(), await self._publish_failed()

        message = await cli.main_async(["outbox", "replay", "--id", str(first)])

        assert message == "1 event(s) back to PENDING"
        async with async_session_factory() as session:
            statuses = dict(
                (await session.execute(select(OutboxEventORM.id, OutboxEventORM.status))).all()
            )
        assert statuses == {first: "PENDING", second: "FAILED"}
