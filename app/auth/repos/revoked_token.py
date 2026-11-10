import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert

from app.auth.models.revoked_token import RevokedTokenORM
from app.core.db import rowcount
from app.core.repo import BaseRepo
from app.core.security import JWT_LEEWAY_SECONDS


class RevokedTokenRepo(BaseRepo[RevokedTokenORM]):
    model = RevokedTokenORM

    async def revoke(self, jti: uuid.UUID, expires_at: datetime) -> bool:
        """Revoke a token. Returns False if it was already revoked.

        A single INSERT ... ON CONFLICT DO NOTHING makes check-and-revoke atomic: of two
        concurrent requests revoking the same jti, only one gets True.
        """
        stmt = (
            insert(RevokedTokenORM)
            .values(jti=jti, expires_at=expires_at)
            .on_conflict_do_nothing(index_elements=[RevokedTokenORM.jti])
            .returning(RevokedTokenORM.jti)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none() is not None

    async def is_revoked(self, jti: uuid.UUID) -> bool:
        stmt = select(exists().where(RevokedTokenORM.jti == jti))
        result = await self.session.execute(stmt)
        return bool(result.scalar())

    async def delete_expired(self) -> int:
        """Delete revocations of tokens that are rejected as expired anyway. Returns how many."""
        # A token is accepted until `exp` plus the leeway: purging its revocation at `exp`
        # would let a used refresh token work once more in that window.
        cutoff = datetime.now(UTC) - timedelta(seconds=JWT_LEEWAY_SECONDS)
        stmt = delete(RevokedTokenORM).where(RevokedTokenORM.expires_at < cutoff)
        return rowcount(await self.session.execute(stmt))
