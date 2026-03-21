from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.models.mixins.id import IntPkMixin


class RoleORM(Base, IntPkMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)

    permissions: Mapped[list["PermissionORM"]] = relationship(
        secondary="role_permissions",
        lazy="selectin",
    )
