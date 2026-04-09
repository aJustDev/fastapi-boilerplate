import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer

import app.models  # noqa: F401 -- register all ORM models in Base.metadata
from app.core.db import Base
from app.core.security import hash_password
from app.models.auth.user import UserORM

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_url(pg_container):
    return pg_container.get_connection_url()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_engine(pg_url):
    engine = create_async_engine(pg_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(async_engine):
    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(session_factory):
    """Yields an AsyncSession that is rolled back after each test.

    Repos only call flush() -- never commit() -- so rollback at the end
    discards all changes and provides full test isolation.
    """
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(loop_scope="session")
async def seed_user(db_session: AsyncSession) -> UserORM:
    user = UserORM(
        email="integration@test.com",
        username="integrationuser",
        password_hash=hash_password("TestPass123!"),
        full_name="Integration Test User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user
