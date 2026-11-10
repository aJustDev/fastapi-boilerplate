from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import AuditMixin, Base, IntPkMixin
from app.workshops.models.workshop import WorkshopORM


class EnrollmentORM(Base, IntPkMixin, AuditMixin):
    __tablename__ = "enrollments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('confirmed', 'waitlisted', 'cancelled', 'attended', 'no_show')",
            name="status",
        ),
        # One enrollment per user and workshop, not counting the ones that were cancelled:
        # someone who left may enrol again, and gets a new row at the end of the list.
        Index(
            "uq_enrollments_workshop_id_attendee_id_current",
            "workshop_id",
            "attendee_id",
            unique=True,
            postgresql_where=text("status <> 'cancelled'"),
        ),
    )

    workshop_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("workshops.id", ondelete="CASCADE"), index=True
    )
    # A user of another context: referenced by id, without an ORM relationship.
    attendee_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str]
    reminded_at: Mapped[datetime | None] = mapped_column(default=None)

    # lazy="raise": in async code a relationship is loaded by the query that needs it
    # (EnrollmentRepo joins it), never by touching the attribute.
    workshop: Mapped[WorkshopORM] = relationship(lazy="raise")
