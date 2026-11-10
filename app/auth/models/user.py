from sqlalchemy import Boolean, Index, Text, func, text
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
    # Every token carries the value this had when it was issued (claim `sv`) and is
    # accepted only while they match. Adding one ends every session of the account at
    # once (a stolen refresh token was replayed). A counter, not a timestamp: `iat` has
    # second precision, and a token issued in the same second as the cut would survive it.
    session_version: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False
    )

    roles: Mapped[list[RoleORM]] = relationship(
        secondary="user_roles",
        lazy="selectin",
    )

    def accepts_session(self, session_version: object) -> bool:
        """Whether a token issued at `session_version` still belongs to a live session."""
        return type(session_version) is int and session_version == self.session_version

    def has_role(self, role_name: str) -> bool:
        return any(r.name == role_name for r in self.roles)

    def has_permission(self, permission_name: str) -> bool:
        return any(p.name == permission_name for r in self.roles for p in r.permissions)
