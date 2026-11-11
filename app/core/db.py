from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any, cast

from sqlalchemy import BigInteger, DateTime, Identity, MetaData, Text, event, func, text
from sqlalchemy.engine import Connection, CursorResult, Result, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings
from app.core.logging.context import get_actor


def _unnamed_statement() -> str:
    # PostgreSQL replaces the unnamed statement with each new one, on whichever server
    # connection: nothing is left behind. A named statement would pile up on the server
    # connections of a transaction pooler (they are never reset between clients), or be
    # missing on the next one.
    return ""


def engine_options(*, transaction_pooler: bool) -> dict[str, Any]:
    """Options of the app's engine; shared with the integration tests that check them.

    Behind a pooler in transaction mode every transaction may run on another server
    connection, so nothing may live on the connection between transactions:
    - asyncpg's and SQLAlchemy's caches of prepared statements are off and statements are
      unnamed: a cached one would be missing on the next server connection, and named ones
      would pile up on the server connections;
    - the timeouts are not sent when connecting, where PgBouncer refuses parameters it does
      not know: `set_timeouts_per_transaction` sets them inside each transaction.
    """
    connect_args: dict[str, Any] = {
        "timeout": settings.DB_CONNECT_TIMEOUT,
        "command_timeout": settings.DB_COMMAND_TIMEOUT,
    }
    if transaction_pooler:
        connect_args |= {
            "statement_cache_size": 0,
            "prepared_statement_cache_size": 0,
            "prepared_statement_name_func": _unnamed_statement,
        }
    else:
        connect_args["server_settings"] = {
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
            "lock_timeout": str(settings.DB_LOCK_TIMEOUT_MS),
        }
    return dict(
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        echo=False,
        # A DBAPIError carries its statement and, by default, the bound values. Its text
        # ends up in the log: without this, a failed INSERT INTO users logs the password hash.
        hide_parameters=True,
        connect_args=connect_args,
    )


_LOCAL_TIMEOUTS = text(
    "SELECT set_config('statement_timeout', :statement_timeout, true),"
    " set_config('lock_timeout', :lock_timeout, true)"
)


def _set_local_timeouts(connection: Connection) -> None:
    # set_config(..., true) is SET LOCAL: it lasts until the end of the transaction, on
    # whichever server connection the pooler lent for it.
    connection.execute(
        _LOCAL_TIMEOUTS,
        {
            "statement_timeout": str(settings.DB_STATEMENT_TIMEOUT_MS),
            "lock_timeout": str(settings.DB_LOCK_TIMEOUT_MS),
        },
    )


def set_timeouts_per_transaction(engine: AsyncEngine) -> None:
    """Start every transaction of `engine` with its statement and lock timeouts.

    For an engine behind a transaction pooler, where they cannot be set per connection.
    It costs one round trip per transaction.
    """
    event.listen(engine.sync_engine, "begin", _set_local_timeouts)


ENGINE_OPTIONS = engine_options(transaction_pooler=settings.DB_TRANSACTION_POOLER)

engine = create_async_engine(settings.DATABASE_URL, **ENGINE_OPTIONS)
if settings.DB_TRANSACTION_POOLER:
    set_timeouts_per_transaction(engine)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


def build_asyncpg_dsn() -> str:
    """Plain DSN for the raw asyncpg LISTEN connections, which live outside the engine.

    LISTEN needs a session of its own: behind a pooler in transaction mode the
    subscription would stay on a server connection lent to someone else, so it uses
    DB_DIRECT_URL when there is one. Otherwise DATABASE_URL, not the DB_* settings:
    DATABASE_URL is only built from DB_* when empty, so setting it directly would point
    the listener at a different database than the pool.
    """
    url = make_url(settings.direct_database_url).set(drivername="postgresql")
    # TLS is `ssl=` for SQLAlchemy's asyncpg dialect and `sslmode=` in an asyncpg DSN.
    query = dict(url.query)
    if "ssl" in query:
        query["sslmode"] = query.pop("ssl")
    return url.set(query=query).render_as_string(hide_password=False)


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
