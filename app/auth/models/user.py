from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models.role import RoleORM
from app.core.db import AuditMixin, Base, IntPkMixin


class UserORM(Base, IntPkMixin, AuditMixin):
    __tablename__ = "users"
    __table_args__ = (
        # Uniqueness ignores case: "Foo@x.com" and "foo@x.com" are the same account.
        Index("uq_users_email_lower", func.lower(text("email")), unique=True),
        Index("uq_users_username_lower", func.lower(text("username")), unique=True),
        Index("ix_users_is_active", "is_active", postgresql_where=text("is_active = true")),
    )

    email: Mapped[str] = mapped_column(Text, nullable=False)
    username: Mapped[str] = mapped_column(Text, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    # Tokens issued before this instant are rejected: set when the account's sessions
    # must end (a stolen refresh token was replayed).
    tokens_valid_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    roles: Mapped[list[RoleORM]] = relationship(
        secondary="user_roles",
        lazy="selectin",
    )

    def accepts_token_issued_at(self, iat: float) -> bool:
        """Whether a token with this `iat` (seconds) was issued after the last invalidation."""
        return self.tokens_valid_after is None or iat >= self.tokens_valid_after.timestamp()

    def has_role(self, role_name: str) -> bool:
        return any(r.name == role_name for r in self.roles)

    def has_permission(self, permission_name: str) -> bool:
        return any(p.name == permission_name for r in self.roles for p in r.permissions)
