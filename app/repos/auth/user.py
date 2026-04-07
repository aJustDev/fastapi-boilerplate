import logging

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.auth.user import UserORM
from app.repos.base import BaseRepo

logger = logging.getLogger(__name__)


class UserRepo(BaseRepo[UserORM]):
    model = UserORM

    async def get_by_email(self, email: str) -> UserORM | None:
        logger.debug("Querying user by email")
        stmt = select(UserORM).options(selectinload(UserORM.roles)).where(UserORM.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str) -> UserORM | None:
        logger.debug("Querying user by username")
        stmt = (
            select(UserORM).options(selectinload(UserORM.roles)).where(UserORM.username == username)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
