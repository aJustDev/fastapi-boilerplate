from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column


class AuditMixin:
    """Adds created_at, updated_at, created_by, updated_by columns."""

    created_at: Mapped[datetime] = mapped_column(
        default=func.now(),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        default=None,
        onupdate=func.now(),
        server_onupdate=func.now(),
    )
    created_by: Mapped[str | None] = mapped_column(default=None)
    updated_by: Mapped[str | None] = mapped_column(default=None)
