"""The two jobs of the context, run the way the job worker runs them: each opens its own
session and commits."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth.models.user import UserORM
from app.core.db import async_session_factory
from app.core.events.models import OutboxEventORM
from app.workshops.jobs.finish import workshops_finish
from app.workshops.jobs.reminders import workshop_reminders
from app.workshops.models import EnrollmentORM, WorkshopORM
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def _workshop_with_attendees(
    starts_in: timedelta, statuses: list[EnrollmentStatus]
) -> tuple[int, list[int]]:
    """A published workshop with one enrollment per status; returns its id and theirs."""
    async with async_session_factory() as session:
        users = [
            UserORM(email=f"u{n}@example.com", username=f"u{n}", password_hash="x")
            for n in range(len(statuses) + 1)
        ]
        session.add_all(users)
        await session.flush()
        starts_at = datetime.now(UTC) + starts_in
        workshop = WorkshopORM(
            organizer_id=users[0].id,
            title="Glazing",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=2),
            capacity=10,
            status=WorkshopStatus.PUBLISHED,
        )
        session.add(workshop)
        await session.flush()
        enrollments = [
            EnrollmentORM(workshop_id=workshop.id, attendee_id=user.id, status=status)
            for user, status in zip(users[1:], statuses, strict=True)
        ]
        session.add_all(enrollments)
        await session.commit()
        return workshop.id, [e.id for e in enrollments]


async def _reminders() -> list[OutboxEventORM]:
    stmt = select(OutboxEventORM).where(OutboxEventORM.event_type == "enrollment.reminder")
    async with async_session_factory() as session:
        return list((await session.execute(stmt)).scalars())


class TestReminders:
    async def test_each_confirmed_attendee_gets_one_event(self, app_database):
        confirmed, waitlisted = EnrollmentStatus.CONFIRMED, EnrollmentStatus.WAITLISTED
        workshop_id, (first, second, _) = await _workshop_with_attendees(
            timedelta(hours=20), [confirmed, confirmed, waitlisted]
        )

        await workshop_reminders()

        published = await _reminders()
        assert sorted(e.aggregate_id for e in published) == sorted([str(first), str(second)])
        assert {e.payload["workshop_id"] for e in published} == {workshop_id}
        assert {e.payload["title"] for e in published} == {"Glazing"}

    async def test_running_again_reminds_nobody_twice(self, app_database):
        await _workshop_with_attendees(timedelta(hours=20), [EnrollmentStatus.CONFIRMED] * 3)

        await workshop_reminders()
        await workshop_reminders()

        assert len(await _reminders()) == 3

    async def test_two_workers_at_once_remind_nobody_twice(self, app_database):
        await _workshop_with_attendees(timedelta(hours=20), [EnrollmentStatus.CONFIRMED] * 6)

        await asyncio.gather(workshop_reminders(), workshop_reminders(), workshop_reminders())

        published = await _reminders()
        assert len(published) == 6
        assert len({e.aggregate_id for e in published}) == 6

    async def test_a_workshop_that_is_not_about_to_start_reminds_nobody(self, app_database):
        await _workshop_with_attendees(timedelta(days=3), [EnrollmentStatus.CONFIRMED])

        await workshop_reminders()

        assert await _reminders() == []


async def test_the_finish_job_closes_what_ended(app_database):
    ended, _ = await _workshop_with_attendees(timedelta(days=-1), [])
    async with async_session_factory() as session:
        organizer_id = await session.scalar(select(UserORM.id))
        starts_at = datetime.now(UTC) + timedelta(days=1)
        upcoming = WorkshopORM(
            organizer_id=organizer_id,
            title="Later",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(hours=1),
            capacity=1,
            status=WorkshopStatus.PUBLISHED,
        )
        session.add(upcoming)
        await session.commit()

    await workshops_finish()

    async with async_session_factory() as session:
        statuses = dict((await session.execute(select(WorkshopORM.id, WorkshopORM.status))).all())
    assert statuses == {ended: "finished", upcoming.id: "published"}
