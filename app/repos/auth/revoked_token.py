import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, exists, select
from sqlalchemy.dialects.postgresql import insert

from app.core.db import rowcount
from app.models.auth.revoked_token import RevokedTokenORM
from app.repos.base import BaseRepo


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
        """Delete revocations of tokens that have expired anyway. Returns how many."""
        stmt = delete(RevokedTokenORM).where(RevokedTokenORM.expires_at < datetime.now(UTC))
        return rowcount(await self.session.execute(stmt))
