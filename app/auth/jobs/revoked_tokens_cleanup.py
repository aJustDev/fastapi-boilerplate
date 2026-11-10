import logging

from app.auth.repos.revoked_token import RevokedTokenRepo
from app.core.db import async_session_factory
from app.core.jobs.registry import job_registry

logger = logging.getLogger(__name__)


@job_registry.register("revoked_tokens_cleanup")
async def revoked_tokens_cleanup() -> None:
    """Delete revocations of tokens that expired: an expired token is rejected anyway.

    Every refresh rotation writes one row, so without this the table only grows.
    """
    async with async_session_factory() as session:
        deleted = await RevokedTokenRepo(session).delete_expired()
        await session.commit()
    logger.info("Deleted %d expired token revocations", deleted)
