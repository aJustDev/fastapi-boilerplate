from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

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


# PgBouncer 1.26.1, pinned by digest: the pooler most managed PostgreSQL put in front.
PGBOUNCER_IMAGE = (
    "edoburu/pgbouncer@sha256:8638aa563607256d3c7440437534195f1066a92b68015d89ae9d6b935b444a6d"
)


@pytest.fixture(scope="session")
def pgbouncer_url(pg_container, pg_url):
    """A pooler in transaction mode in front of the test database, as a URL for the app.

    The worst case on purpose: two server connections, so a client's transactions move
    between them, and no support for prepared statements (`max_prepared_statements = 0`),
    like the poolers that have none.
    """
    networks = pg_container.get_wrapped_container().attrs["NetworkSettings"]["Networks"]
    postgres_ip = next(iter(networks.values()))["IPAddress"]
    database = make_url(pg_url)
    pooler = (
        DockerContainer(PGBOUNCER_IMAGE)
        .with_env("DB_HOST", postgres_ip)
        .with_env("DB_PORT", "5432")
        .with_env("DB_USER", database.username)
        .with_env("DB_PASSWORD", database.password)
        .with_env("DB_NAME", database.database)
        .with_env("AUTH_TYPE", "scram-sha-256")
        .with_env("POOL_MODE", "transaction")
        .with_env("DEFAULT_POOL_SIZE", "2")
        .with_env("MAX_PREPARED_STATEMENTS", "0")
        .with_exposed_ports(5432)
        .waiting_for(LogMessageWaitStrategy("process up"))
    )
    with pooler:
        yield database.set(
            host=pooler.get_container_host_ip(), port=int(pooler.get_exposed_port(5432))
        ).render_as_string(hide_password=False)


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
async def app_database(pg_url, async_engine) -> AsyncGenerator[None]:
    """The app's own session factory, pointed at the test database.

    For everything that opens its sessions itself through `async_session_factory`: a
    request (`get_session`), the CLI, a use case with a transaction of its own.
    `configure(bind=...)` re-points the factory object every module already imported.
    The rows a request can write are removed after the test.
    """
    engine = create_async_engine(pg_url, poolclass=NullPool)
    async_session_factory.configure(bind=engine)
    try:
        yield
    finally:
        async_session_factory.configure(bind=app_engine)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {_API_TABLES} RESTART IDENTITY CASCADE"))
        await engine.dispose()


@pytest_asyncio.fixture(loop_scope="session")
async def api_client(app_database) -> AsyncGenerator[AsyncClient]:
    """HTTP client over the real app and the test database, with nothing overridden.

    The request runs the real `get_session`, so commits, rollbacks and constraint errors
    are the ones production has. `raise_app_exceptions=False` makes the client see the
    500 a real client would get.
    """
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


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
