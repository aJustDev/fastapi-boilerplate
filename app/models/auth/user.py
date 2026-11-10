from datetime import datetime

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.auth.role import RoleORM
from app.models.mixins.audit import AuditMixin
from app.models.mixins.id import IntPkMixin


class UserORM(Base, IntPkMixin, AuditMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str | None] = mapped_column(Text, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
