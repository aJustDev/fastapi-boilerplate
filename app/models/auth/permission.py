from sqlalchemy import Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.mixins.id import IntPkMixin


class PermissionORM(Base, IntPkMixin):
    __tablename__ = "permissions"

    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
