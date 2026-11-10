from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import NamedTuple

from sqlalchemy import Select, func, select, update
from sqlalchemy.orm import joinedload

from app.core.repo import BaseRepo, FieldMapping
from app.workshops.models.enrollment import EnrollmentORM
from app.workshops.models.workshop import WorkshopORM
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus

# Enrollments that can still change hands: the ones a cancellation or a departure ends.
OPEN = (EnrollmentStatus.CONFIRMED, EnrollmentStatus.WAITLISTED)


class DueReminder(NamedTuple):
    enrollment_id: int
    workshop_id: int
    attendee_id: int
    title: str
    starts_at: datetime


class EnrollmentRepo(BaseRepo[EnrollmentORM]):
    model = EnrollmentORM
    map_field: dict[str, FieldMapping] = {
        "status": {"column": EnrollmentORM.status, "op": "eq"},
        "workshop_id": {"column": EnrollmentORM.workshop_id, "op": "eq"},
        "attendee_id": {"column": EnrollmentORM.attendee_id, "op": "eq"},
    }

    def _base_select(self) -> Select:
        # An enrollment is read together with its workshop, in one query: the relationship
        # is lazy="raise" and a join to one row costs less than a second round trip.
        return select(EnrollmentORM).options(joinedload(EnrollmentORM.workshop))

    async def get_current(self, workshop_id: int, attendee_id: int) -> EnrollmentORM | None:
        """The enrollment of a user in a workshop that was not cancelled: at most one."""
        stmt = self._base_select().where(
            EnrollmentORM.workshop_id == workshop_id,
            EnrollmentORM.attendee_id == attendee_id,
            EnrollmentORM.status != EnrollmentStatus.CANCELLED,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def waitlist_head(self, workshop_id: int, limit: int) -> list[EnrollmentORM]:
        """The first `limit` people waiting, in the order they enrolled.

        Ids grow in that order: enrollments of one workshop are inserted under its lock.
        """
        stmt = (
            self._base_select()
            .where(
                EnrollmentORM.workshop_id == workshop_id,
                EnrollmentORM.status == EnrollmentStatus.WAITLISTED,
            )
            .order_by(EnrollmentORM.id)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def cancel_open(self, workshop_id: int) -> Sequence[tuple[int, int]]:
        """Cancel every confirmed or waiting enrollment of a workshop, in one statement.

        Returns `(enrollment_id, attendee_id)` of each one.
        """
        result = await self.session.execute(
            update(EnrollmentORM)
            .where(EnrollmentORM.workshop_id == workshop_id, EnrollmentORM.status.in_(OPEN))
            .values(status=EnrollmentStatus.CANCELLED)
            .returning(EnrollmentORM.id, EnrollmentORM.attendee_id)
        )
        return [(row.id, row.attendee_id) for row in result]

    async def claim_due_reminders(self, *, within: timedelta, limit: int) -> list[DueReminder]:
        """Mark as reminded up to `limit` confirmed enrollments of workshops that start
        in the next `within`, and return them.

        SKIP LOCKED: a row another transaction is changing (someone leaving, another
        worker on the same batch) is left for the next run instead of waited for. Marking
        and returning in one transaction means a reminder is claimed once.
        """
        due = (
            select(
                EnrollmentORM.id,
                EnrollmentORM.workshop_id,
                EnrollmentORM.attendee_id,
                WorkshopORM.title,
                WorkshopORM.starts_at,
            )
            .join(WorkshopORM, WorkshopORM.id == EnrollmentORM.workshop_id)
            .where(
                EnrollmentORM.status == EnrollmentStatus.CONFIRMED,
                EnrollmentORM.reminded_at.is_(None),
                WorkshopORM.status == WorkshopStatus.PUBLISHED,
                WorkshopORM.starts_at > func.now(),
                WorkshopORM.starts_at <= func.now() + within,
            )
            .order_by(EnrollmentORM.id)
            .limit(limit)
            .with_for_update(of=EnrollmentORM, skip_locked=True)
        )
        rows = [DueReminder(*row) for row in await self.session.execute(due)]
        if rows:
            await self.session.execute(
                update(EnrollmentORM)
                .where(EnrollmentORM.id.in_([row.enrollment_id for row in rows]))
                .values(reminded_at=func.now())
            )
        return rows
