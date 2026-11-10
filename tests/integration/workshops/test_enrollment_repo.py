"""EnrollmentRepo against PostgreSQL: one enrollment per person, the waiting list in
order, a cancellation in one statement, and the reminders that are due."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]

CONFIRMED, WAITLISTED, CANCELLED, ATTENDED, NO_SHOW = EnrollmentStatus
DAY = timedelta(hours=24)


@pytest.fixture
def repo(db_session: AsyncSession) -> EnrollmentRepo:
    return EnrollmentRepo(db_session)


class TestOnePerPerson:
    async def test_a_second_enrollment_in_the_same_workshop_is_refused(
        self, db_session: AsyncSession, users, make_workshop, make_enrollment
    ):
        workshop = await make_workshop()
        await make_enrollment(workshop, users[1], WAITLISTED)

        with pytest.raises(IntegrityError, match="uq_enrollments_workshop_id_attendee_id_current"):
            await make_enrollment(workshop, users[1], CONFIRMED)
        await db_session.rollback()

    async def test_who_cancelled_may_enrol_again(
        self, repo: EnrollmentRepo, users, make_workshop, make_enrollment
    ):
        workshop = await make_workshop()
        await make_enrollment(workshop, users[1], CANCELLED)
        await make_enrollment(workshop, users[1], CANCELLED)
        again = await make_enrollment(workshop, users[1], WAITLISTED)

        current = await repo.get_current(workshop.id, users[1].id)

        assert current is not None
        assert current.id == again.id

    async def test_no_current_enrollment_is_none(
        self, repo: EnrollmentRepo, users, make_workshop, make_enrollment
    ):
        workshop = await make_workshop()
        await make_enrollment(workshop, users[1], CANCELLED)
        await make_enrollment(workshop, users[2], CONFIRMED)

        assert await repo.get_current(workshop.id, users[1].id) is None


async def test_an_enrollment_is_read_together_with_its_workshop(
    repo: EnrollmentRepo, db_session: AsyncSession, users, make_workshop, make_enrollment
):
    workshop = await make_workshop(title="Glazing")
    stored = await make_enrollment(workshop, users[1])
    db_session.expunge_all()  # forget everything: what comes back is what the query loaded

    loaded = await repo.get_by_id(stored.id)

    assert loaded is not None
    assert "workshop" not in inspect(loaded).unloaded
    assert loaded.workshop.title == "Glazing"


class TestWaitlistHead:
    async def test_returns_who_waits_in_the_order_they_enrolled(
        self, repo: EnrollmentRepo, users, make_workshop, make_enrollment
    ):
        workshop, other = await make_workshop(), await make_workshop()
        await make_enrollment(workshop, users[0], CONFIRMED)
        first = await make_enrollment(workshop, users[1], WAITLISTED)
        await make_enrollment(workshop, users[2], CANCELLED)
        await make_enrollment(other, users[2], WAITLISTED)
        second = await make_enrollment(workshop, users[3], WAITLISTED)
        third = await make_enrollment(workshop, users[4], WAITLISTED)

        head = await repo.waitlist_head(workshop.id, 2)
        everyone = await repo.waitlist_head(workshop.id, 10)

        assert [e.id for e in head] == [first.id, second.id]
        assert [e.id for e in everyone] == [first.id, second.id, third.id]


class TestCancelOpen:
    async def test_cancels_who_is_seated_or_waiting_and_returns_them(
        self, repo: EnrollmentRepo, db_session: AsyncSession, users, make_workshop, make_enrollment
    ):
        workshop, other = await make_workshop(), await make_workshop()
        seated = await make_enrollment(workshop, users[1], CONFIRMED)
        waiting = await make_enrollment(workshop, users[2], WAITLISTED)
        attended = await make_enrollment(workshop, users[3], ATTENDED)
        gone = await make_enrollment(workshop, users[4], CANCELLED)
        elsewhere = await make_enrollment(other, users[1], CONFIRMED)

        cancelled = await repo.cancel_open(workshop.id)

        assert sorted(cancelled) == [(seated.id, users[1].id), (waiting.id, users[2].id)]
        for enrollment in (seated, waiting, attended, gone, elsewhere):
            await db_session.refresh(enrollment)
        assert (seated.status, waiting.status) == (CANCELLED, CANCELLED)
        assert (attended.status, elsewhere.status) == (ATTENDED, CONFIRMED)
        assert seated.updated_at is not None
        assert gone.updated_at is None  # already cancelled: not touched again

    async def test_nothing_to_cancel_returns_nothing(self, repo: EnrollmentRepo, make_workshop):
        assert await repo.cancel_open((await make_workshop()).id) == []


class TestDueReminders:
    async def test_claims_confirmed_enrollments_of_workshops_about_to_start(
        self, repo: EnrollmentRepo, db_session: AsyncSession, users, make_workshop, make_enrollment
    ):
        tomorrow = await make_workshop(title="Tomorrow", starts_in=timedelta(hours=20))
        due = await make_enrollment(tomorrow, users[1])
        await make_enrollment(tomorrow, users[2], WAITLISTED)
        await make_enrollment(tomorrow, users[3], CANCELLED)
        next_week = await make_workshop(starts_in=timedelta(days=7))
        await make_enrollment(next_week, users[1])
        started = await make_workshop(starts_in=timedelta(hours=-1))
        await make_enrollment(started, users[1])
        cancelled = await make_workshop(
            starts_in=timedelta(hours=20), status=WorkshopStatus.CANCELLED
        )
        await make_enrollment(cancelled, users[1])

        claimed = await repo.claim_due_reminders(within=DAY, limit=100)

        assert [row.enrollment_id for row in claimed] == [due.id]
        (row,) = claimed
        assert (row.workshop_id, row.attendee_id, row.title) == (
            tomorrow.id,
            users[1].id,
            "Tomorrow",
        )
        assert row.starts_at == tomorrow.starts_at
        await db_session.refresh(due)
        assert due.reminded_at is not None

    async def test_a_reminder_is_claimed_once(
        self, repo: EnrollmentRepo, users, make_workshop, make_enrollment
    ):
        tomorrow = await make_workshop(starts_in=timedelta(hours=20))
        await make_enrollment(tomorrow, users[1])
        await make_enrollment(tomorrow, users[2], reminded_at=datetime.now(UTC))

        first = await repo.claim_due_reminders(within=DAY, limit=100)
        second = await repo.claim_due_reminders(within=DAY, limit=100)

        assert (len(first), len(second)) == (1, 0)

    async def test_a_run_takes_at_most_its_batch_and_the_next_one_the_rest(
        self, repo: EnrollmentRepo, users, make_workshop, make_enrollment
    ):
        tomorrow = await make_workshop(starts_in=timedelta(hours=20), capacity=5)
        enrolled = [await make_enrollment(tomorrow, user) for user in users]

        first = await repo.claim_due_reminders(within=DAY, limit=3)
        second = await repo.claim_due_reminders(within=DAY, limit=3)

        assert [row.enrollment_id for row in first] == [e.id for e in enrolled[:3]]
        assert [row.enrollment_id for row in second] == [e.id for e in enrolled[3:]]
