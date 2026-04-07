import uuid
from datetime import datetime

from sqlalchemy import exists, select

from app.models.auth.revoked_token import RevokedTokenORM
from app.repos.base import BaseRepo


class RevokedTokenRepo(BaseRepo[RevokedTokenORM]):
    model = RevokedTokenORM

    async def revoke(self, jti: uuid.UUID, expires_at: datetime) -> RevokedTokenORM:
        token = RevokedTokenORM(jti=jti, expires_at=expires_at)
        self.session.add(token)
        await self.session.flush()
        return token

    async def is_revoked(self, jti: uuid.UUID) -> bool:
        stmt = select(exists().where(RevokedTokenORM.jti == jti))
        result = await self.session.execute(stmt)
        return bool(result.scalar())
