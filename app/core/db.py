from collections.abc import AsyncGenerator
from typing import Any, cast

from sqlalchemy.engine import CursorResult, Result, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_pre_ping=True,
    echo=False,
)

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


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
