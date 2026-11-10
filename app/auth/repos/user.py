import logging
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.auth.models.user import UserORM
from app.core.repo import BaseRepo

logger = logging.getLogger(__name__)


class UserRepo(BaseRepo[UserORM]):
    model = UserORM

    # Lookups are case-insensitive, like the unique indexes on LOWER(email) and
    # LOWER(username): "Foo@x.com" is the same account as "foo@x.com".

    async def get_by_email(self, email: str) -> UserORM | None:
        logger.debug("Querying user by email")
        stmt = (
            select(UserORM)
            .options(selectinload(UserORM.roles))
            .where(func.lower(UserORM.email) == email.lower())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str) -> UserORM | None:
        logger.debug("Querying user by username")
        stmt = (
            select(UserORM)
            .options(selectinload(UserORM.roles))
            .where(func.lower(UserORM.username) == username.lower())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def invalidate_tokens(self, user_id: int, at: datetime) -> None:
        stmt = update(UserORM).where(UserORM.id == user_id).values(tokens_valid_after=at)
        await self.session.execute(stmt)
