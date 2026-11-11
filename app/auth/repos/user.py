from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.auth.models.role import RoleORM
from app.auth.models.user import UserORM
from app.core.repo import BaseRepo


class UserRepo(BaseRepo[UserORM]):
    model = UserORM

    # Lookups are case-insensitive, like the unique indexes on LOWER(email) and
    # LOWER(username): "Foo@x.com" is the same account as "foo@x.com".

    async def get_by_email(self, email: str) -> UserORM | None:
        stmt = (
            select(UserORM)
            .options(selectinload(UserORM.roles))
            .where(func.lower(UserORM.email) == email.lower())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_username(self, username: str) -> UserORM | None:
        stmt = (
            select(UserORM)
            .options(selectinload(UserORM.roles))
            .where(func.lower(UserORM.username) == username.lower())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_role(self, name: str) -> RoleORM | None:
        result = await self.session.execute(select(RoleORM).where(RoleORM.name == name))
        return result.scalars().first()

    async def end_sessions(self, user_id: int) -> None:
        """Bump the session version: no token issued so far is accepted any more."""
        # Incremented in SQL: two invalidations at once must not lose one.
        stmt = (
            update(UserORM)
            .where(UserORM.id == user_id)
            .values(session_version=UserORM.session_version + 1)
        )
        await self.session.execute(stmt)
