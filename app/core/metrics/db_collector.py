from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from app.core.metrics.instruments import (
    db_pool_checked_in,
    db_pool_checked_out,
    db_pool_overflow,
    db_pool_size,
)


def update_db_pool_metrics(engine: AsyncEngine) -> None:
    """Read current pool statistics from SQLAlchemy and update Prometheus gauges."""
    pool = engine.pool
    # Only queue pools keep these counters (NullPool, used by some tests, does not).
    if not isinstance(pool, QueuePool):
        return
    db_pool_size.set(pool.size())
    db_pool_checked_out.set(pool.checkedout())
    db_pool_checked_in.set(pool.checkedin())
    db_pool_overflow.set(pool.overflow())
