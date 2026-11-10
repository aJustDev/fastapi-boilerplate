from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import AuditMixin, Base, IntPkMixin


class WorkshopORM(Base, IntPkMixin, AuditMixin):
    __tablename__ = "workshops"
    __table_args__ = (
        # The rules the services enforce, as the last line of defence: a bug or a script
        # that skips them fails here instead of storing an impossible workshop.
        CheckConstraint("ends_at > starts_at", name="ends_after_start"),
        CheckConstraint("capacity >= 1", name="capacity_positive"),
        CheckConstraint(
            "seats_taken >= 0 AND seats_taken <= capacity", name="seats_within_capacity"
        ),
        CheckConstraint("status IN ('draft', 'published', 'cancelled', 'finished')", name="status"),
        # The order of the public listing and of its cursor.
        Index("ix_workshops_starts_at_id", "starts_at", "id"),
        # What the workshops_finish job looks for.
        Index(
            "ix_workshops_ends_at_published",
            "ends_at",
            postgresql_where=text("status = 'published'"),
        ),
    )

    # A user of another context: referenced by id, without an ORM relationship.
    organizer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str]
    description: Mapped[str | None] = mapped_column(default=None)
    starts_at: Mapped[datetime]
    ends_at: Mapped[datetime]
    capacity: Mapped[int] = mapped_column(Integer)
    # Enrollments that hold a seat. Kept on the row, under its lock, so a listing shows
    # the free seats without counting (see app/workshops/services/seating.py).
    seats_taken: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    status: Mapped[str] = mapped_column(default="draft", server_default="draft")
    # Counts the edits of the organizer: a PATCH states the version it started from.
    version: Mapped[int] = mapped_column(Integer, default=1, server_default=text("1"))
