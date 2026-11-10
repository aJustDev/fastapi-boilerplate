"""The errors PostgreSQL and asyncpg really raise map to the status the handlers promise.

The handlers read `sqlstate` and the driver exception from SQLAlchemy's wrapper; these
tests pin those attributes against the real stack instead of hand-made exceptions.
"""

import pytest
from sqlalchemy import Insert, insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from app.auth.models.associations import user_roles
from app.auth.models.user import UserORM
from app.core.exceptions.handlers import database_error_handler, integrity_error_handler

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

REQUEST = Request(
    {"type": "http", "method": "POST", "path": "/v1/x", "headers": [], "query_string": b""}
)
USER = {"email": "someone@example.com", "username": "someone", "password_hash": "x"}


async def _status(session: AsyncSession, statement: Insert) -> int:
    with pytest.raises(DBAPIError) as raised:
        await session.execute(statement)
    await session.rollback()
    handler = (
        integrity_error_handler
        if type(raised.value).__name__ == "IntegrityError"
        else database_error_handler
    )
    return (await handler(REQUEST, raised.value)).status_code  # type: ignore[arg-type]


async def test_duplicate_is_a_conflict(db_session: AsyncSession, seed_user: UserORM):
    duplicate = insert(UserORM).values(USER | {"email": seed_user.email})

    assert await _status(db_session, duplicate) == 409


@pytest.mark.parametrize(
    "values",
    [
        {"email": None},  # NOT NULL violation, raised by PostgreSQL
        {"full_name": "a\x00b"},  # invalid byte sequence, raised by PostgreSQL
        {"session_version": 2**40},  # refused by asyncpg before it is sent
    ],
    ids=["not-null", "nul-byte", "int-out-of-range"],
)
async def test_a_value_the_column_cannot_take_is_a_422(db_session: AsyncSession, values: dict):
    assert await _status(db_session, insert(UserORM).values(USER | values)) == 422


async def test_a_broken_reference_is_a_conflict(db_session: AsyncSession):
    orphan = insert(user_roles).values(user_id=999_999_999, role_id=999_999_999)

    assert await _status(db_session, orphan) == 409
