from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AuditMixin, Base, IntPkMixin


class ItemORM(Base, IntPkMixin, AuditMixin):
    __tablename__ = "items"
    __table_args__ = (
        Index("ix_items_is_active", "is_active", postgresql_where=text("is_active = true")),
        Index("ix_items_created_at", "created_at"),
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(
        Text, nullable=False, default="general", server_default="general", index=True
    )
    priority: Mapped[int] = mapped_column(
        default=0, server_default=text("0"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    owner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
