from app.auth.repos.revoked_token import RevokedTokenRepo
from app.core.db import async_session_factory
from app.core.jobs.registry import job_registry


@job_registry.register("revoked_tokens_cleanup")
async def revoked_tokens_cleanup() -> str | None:
    """Delete revocations of tokens that expired: an expired token is rejected anyway.

    Every refresh rotation writes one row, so without this the table only grows.
    """
    async with async_session_factory() as session:
        deleted = await RevokedTokenRepo(session).delete_expired()
        await session.commit()
    return f"{deleted} expired revocation{'s' * (deleted != 1)} deleted" if deleted else None
