"""The errors PostgreSQL and asyncpg really raise map to the status the handlers promise.

The handlers read `sqlstate` and the driver exception from SQLAlchemy's wrapper; these
tests pin those attributes against the real stack instead of hand-made exceptions.
"""

import pytest
from sqlalchemy import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.auth.models.user import UserORM
from app.core.exceptions.handlers import database_error_handler, integrity_error_handler
from app.items.models.item import ItemORM

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

REQUEST = Request(
    {"type": "http", "method": "POST", "path": "/v1/x", "headers": [], "query_string": b""}
)


async def _status(session: AsyncSession, values: dict) -> int:
    with pytest.raises(DBAPIError) as raised:
        await session.execute(insert(ItemORM).values(**values))
    await session.rollback()
    handler = (
        integrity_error_handler
        if type(raised.value).__name__ == "IntegrityError"
        else database_error_handler
    )
    return (await handler(REQUEST, raised.value)).status_code  # type: ignore[arg-type]


async def test_duplicate_is_a_conflict(db_session: AsyncSession, seed_user: UserORM):
    values = {"email": seed_user.email, "username": "other", "password_hash": "x"}
    with pytest.raises(DBAPIError) as raised:
        await db_session.execute(insert(UserORM).values(**values))
    await db_session.rollback()

    response = await integrity_error_handler(REQUEST, raised.value)  # type: ignore[arg-type]

    assert response.status_code == 409


@pytest.mark.parametrize(
    "values",
    [
        {"name": None},  # NOT NULL violation, raised by PostgreSQL
        {"name": "a\x00b"},  # invalid byte sequence, raised by PostgreSQL
        {"name": "x", "priority": 2**40},  # refused by asyncpg before it is sent
    ],
    ids=["not-null", "nul-byte", "int-out-of-range"],
)
async def test_a_value_the_column_cannot_take_is_a_422(db_session: AsyncSession, values: dict):
    user = UserORM(email="owner@example.com", username="owner", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    assert await _status(db_session, {"owner_id": user.id} | values) == 422


async def test_a_broken_reference_is_a_conflict(db_session: AsyncSession):
    assert await _status(db_session, {"name": "x", "owner_id": 999_999_999}) == 409
