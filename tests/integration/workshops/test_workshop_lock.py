"""`get_for_update` holds the row: a second transaction waits for the first to end.

Two real transactions, so nothing here can run inside the rolled-back `db_session`.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request

from app.auth.models.user import UserORM
from app.core.exceptions.handlers import database_error_handler
from app.workshops.models import WorkshopORM
from app.workshops.repos.workshop import WorkshopRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


REQUEST = Request(
    {"type": "http", "method": "POST", "path": "/v1/x", "headers": [], "query_string": b""}
)


@pytest.fixture
def committing_tables() -> list[str]:
    return ["workshops", "users"]


async def test_a_locked_workshop_makes_the_next_transaction_wait(committing_factory):
    async with committing_factory() as setup:
        organizer = UserORM(email="org@example.com", username="org", password_hash="x")
        setup.add(organizer)
        await setup.flush()
        start = datetime.now(UTC) + timedelta(days=1)
        workshop = WorkshopORM(
            organizer_id=organizer.id,
            title="Pottery",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
            capacity=1,
        )
        setup.add(workshop)
        await setup.commit()

    async with committing_factory() as first, committing_factory() as second:
        assert await WorkshopRepo(first).get_for_update(workshop.id) is not None
        # Give up after 200 ms instead of waiting for `first` to end.
        await second.execute(text("SET LOCAL lock_timeout = '200ms'"))

        with pytest.raises(DBAPIError) as refused:
            await WorkshopRepo(second).get_for_update(workshop.id)
        await second.rollback()
        assert refused.value.orig.sqlstate == "55P03"  # lock_not_available
        # What a request that hits it answers: nothing stored, worth sending again.
        response = await database_error_handler(REQUEST, refused.value)
        assert (response.status_code, response.headers["Retry-After"]) == (503, "1")
        assert json.loads(response.body)["code"] == "busy"

        # A plain read does not wait: listing and showing workshops is never held up.
        assert await WorkshopRepo(second).get_by_id(workshop.id) is not None

        await first.commit()
        assert await WorkshopRepo(second).get_for_update(workshop.id) is not None
