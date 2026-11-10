from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, cast

from sqlalchemy import BigInteger, DateTime, Identity, MetaData, Text, func
from sqlalchemy.engine import CursorResult, Result, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings
from app.core.logging.context import get_actor

# Shared by the app engine and the integration test that checks the server settings.
ENGINE_OPTIONS: dict[str, Any] = dict(
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=False,
    # A DBAPIError carries its statement and, by default, the bound values. Its text ends
    # up in the log: without this, a failed INSERT INTO users logs the password hash.
    hide_parameters=True,
    connect_args={
        "timeout": settings.DB_CONNECT_TIMEOUT,
        "command_timeout": settings.DB_COMMAND_TIMEOUT,
        "server_settings": {
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
            "lock_timeout": str(settings.DB_LOCK_TIMEOUT_MS),
        },
    },
)

engine = create_async_engine(settings.DATABASE_URL, **ENGINE_OPTIONS)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


def build_asyncpg_dsn() -> str:
    """Plain DSN for the raw asyncpg LISTEN connections, which live outside the engine.

    Derived from DATABASE_URL, not from the DB_* settings: DATABASE_URL is only built
    from DB_* when empty, so setting it directly (pgbouncer, managed provider) would
    otherwise point the listener at a different database than the pool.
    """
    return (
        make_url(settings.DATABASE_URL)
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )


def rowcount(result: Result[Any]) -> int:
    """Rows affected by an UPDATE or DELETE.

    `AsyncSession.execute` is typed as returning Result; for DML it is a CursorResult,
    which is the one exposing rowcount.
    """
    return cast("CursorResult[Any]", result).rowcount


# Deterministic constraint and index names: Alembic needs a name to drop or alter
# anything, and generated names would differ between databases.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Every timestamp is timezone-aware and every unbounded string is TEXT, like the
    # database; a column declares another type explicitly when it needs one.
    type_annotation_map = {datetime: DateTime(timezone=True), str: Text}


class IntPkMixin:
    """Provides a BIGINT GENERATED ALWAYS AS IDENTITY primary key."""

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )


class AuditMixin:
    """Adds created_at, updated_at, created_by, updated_by columns."""

    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        default=None,
        onupdate=func.now(),
        server_onupdate=func.now(),
    )
    # The id of the authenticated user who made the change (see `actor_var`); NULL for
    # rows written outside a request (workers, jobs, scripts, migrations).
    created_by: Mapped[str | None] = mapped_column(default=get_actor)
    updated_by: Mapped[str | None] = mapped_column(default=None, onupdate=get_actor)


async def get_session() -> AsyncGenerator[AsyncSession]:
    """One session per request: commit if the endpoint returned, roll back if it raised.

    Declare it as `Depends(get_session, scope="function")` (app/deps does): the commit is
    then part of the request, so its failure reaches the client as an error.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
