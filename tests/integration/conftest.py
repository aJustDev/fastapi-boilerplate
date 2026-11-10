from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer

import app.db_registry  # noqa: F401 -- register all ORM models in Base.metadata
from app.auth.models.user import UserORM
from app.core.db import Base, async_session_factory
from app.core.db import engine as app_engine
from app.core.security import hash_password
from main import app
from tests.integration.alembic_helpers import run_alembic

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:18-alpine", driver="asyncpg") as pg:
        yield pg


@pytest.fixture(scope="session")
def pg_url(pg_container):
    return pg_container.get_connection_url()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_engine(pg_url):
    """Engine on a database built by the migrations, the same way production is.

    `create_all` would build the schema from the ORM and hide any drift between the
    models and the migrations. AUTOCOMMIT lets migrations that need it run their own
    statements outside a transaction (CREATE INDEX CONCURRENTLY).
    """
    engine = create_async_engine(pg_url, echo=False)
    async with engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await autocommit.run_sync(run_alembic)
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


@pytest.fixture
def committing_tables() -> list[str]:
    """Tables a test using `committing_factory` writes to. Override it in the test module."""
    return []


@pytest_asyncio.fixture(loop_scope="session")
async def committing_factory(pg_url, async_engine, committing_tables):
    """Session factory whose commits are real, for code that opens its own transactions.

    Workers, and anything that must survive the rollback of a request, cannot run inside
    `db_session`. This factory uses its own NullPool engine (no connection is shared
    between concurrent tasks) and empties `committing_tables` before and after the test.
    Only those tables: never the ones other tests rely on.
    """
    engine = create_async_engine(pg_url, poolclass=NullPool)
    tables = [Base.metadata.tables[name] for name in committing_tables]

    async def _clean() -> None:
        async with engine.begin() as conn:
            for table in tables:
                await conn.execute(table.delete())

    await _clean()
    yield async_sessionmaker(engine, expire_on_commit=False)
    await _clean()
    await engine.dispose()


# What a request can write. Reference data (roles, permissions, scheduled_jobs) comes
# from the migrations and stays; CASCADE reaches user_roles and the tables owned by users.
_API_TABLES = "users, revoked_tokens, outbox_events"


@pytest_asyncio.fixture(loop_scope="session")
async def api_client(pg_url, async_engine) -> AsyncGenerator[AsyncClient]:
    """HTTP client over the real app, with the app's own session factory on the test database.

    Nothing is overridden: the request runs the real `get_session`, so commits, rollbacks
    and constraint errors are the ones production has. `configure(bind=...)` re-points the
    factory object every module already imported. Rows are removed after the test.
    `raise_app_exceptions=False` makes the client see the 500 a real client would get.
    """
    engine = create_async_engine(pg_url, poolclass=NullPool)
    async_session_factory.configure(bind=engine)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        async_session_factory.configure(bind=app_engine)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {_API_TABLES} RESTART IDENTITY CASCADE"))
        await engine.dispose()


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
