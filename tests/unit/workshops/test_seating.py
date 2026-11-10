"""Who gets a seat, who waits, and who is told. Repository and bus are mocked: the rules
under real concurrency are in tests/integration/api/test_workshop_concurrency.py."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.workshops.exceptions import EnrollmentClosedError
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.services.seating import SeatingService
from tests._workshops import enrollment, workshop

CONFIRMED, WAITLISTED, CANCELLED, *_ = EnrollmentStatus


@pytest.fixture
def repo() -> AsyncMock:
    repo = AsyncMock()
    repo.get_current.return_value = None
    repo.waitlist_head.return_value = []

    async def create(entity):
        entity.id = 500
        return entity

    repo.create.side_effect = create
    return repo


@pytest.fixture
def bus() -> AsyncMock:
    bus = AsyncMock()
    bus.publish_many.side_effect = lambda _type, events: len(list(events))
    return bus


@pytest.fixture
def seating(repo: AsyncMock, bus: AsyncMock) -> SeatingService:
    return SeatingService(repo, bus)


class TestEnroll:
    async def test_a_free_seat_is_taken_and_announced(self, seating, bus):
        w = workshop(capacity=2, seats_taken=1)

        created, is_new = await seating.enroll(w, attendee_id=7)

        assert (created.status, is_new) == (CONFIRMED, True)
        assert w.seats_taken == 2
        (event_type, payload), kwargs = bus.publish.call_args
        assert event_type == "enrollment.confirmed"
        assert payload["attendee_id"] == 7
        assert payload["workshop_id"] == w.id
        assert kwargs == {"aggregate_id": created.id}

    async def test_a_full_workshop_puts_the_user_on_the_waiting_list(self, seating, bus):
        w = workshop(capacity=2, seats_taken=2)

        created, is_new = await seating.enroll(w, attendee_id=7)

        assert (created.status, is_new) == (WAITLISTED, True)
        assert w.seats_taken == 2
        bus.publish.assert_not_called()

    async def test_enrolling_twice_returns_the_enrollment_that_exists(self, seating, repo, bus):
        existing = enrollment(status=WAITLISTED)
        repo.get_current.return_value = existing
        w = workshop(seats_taken=0)

        found, is_new = await seating.enroll(w, existing.attendee_id)

        assert (found, is_new) == (existing, False)
        assert w.seats_taken == 0
        repo.create.assert_not_called()
        bus.publish.assert_not_called()

    async def test_a_repeat_is_answered_even_after_enrollment_closed(self, seating, repo):
        # The client that repeats a request must get the same answer, not a new error.
        existing = enrollment()
        repo.get_current.return_value = existing

        found, _ = await seating.enroll(workshop(starts_in=timedelta(hours=-1)), 2)

        assert found is existing

    async def test_a_workshop_that_started_takes_nobody(self, seating, repo):
        with pytest.raises(EnrollmentClosedError):
            await seating.enroll(workshop(starts_in=timedelta(hours=-1)), attendee_id=7)

        repo.create.assert_not_called()


class TestRelease:
    async def test_a_confirmed_seat_goes_to_the_first_person_waiting(self, seating, repo, bus):
        w = workshop(capacity=1, seats_taken=1)
        leaving = enrollment(id=1, attendee_id=2)
        waiting = enrollment(id=2, attendee_id=3, status=WAITLISTED)
        repo.waitlist_head.return_value = [waiting]

        await seating.release(w, leaving)

        assert leaving.status == CANCELLED
        assert waiting.status == CONFIRMED
        assert w.seats_taken == 1  # one left, one came in
        repo.waitlist_head.assert_awaited_once_with(w.id, 1)
        assert bus.publish.call_args.args[0] == "enrollment.cancelled"
        assert bus.publish.call_args.args[1]["reason"] == "left"
        event_type, promoted = bus.publish_many.call_args.args
        assert event_type == "enrollment.promoted"
        assert [aggregate_id for aggregate_id, _ in promoted] == [waiting.id]

    async def test_with_nobody_waiting_the_seat_stays_free(self, seating, bus):
        w = workshop(capacity=2, seats_taken=2)

        await seating.release(w, enrollment())

        assert w.seats_taken == 1
        assert bus.publish_many.call_args.args == ("enrollment.promoted", [])

    async def test_leaving_the_waiting_list_frees_no_seat(self, seating, repo):
        w = workshop(capacity=1, seats_taken=1)
        waiting = enrollment(status=WAITLISTED)

        await seating.release(w, waiting)

        assert waiting.status == CANCELLED
        assert w.seats_taken == 1
        repo.waitlist_head.assert_not_called()

    async def test_nobody_leaves_once_it_started(self, seating):
        leaving = enrollment()

        with pytest.raises(EnrollmentClosedError):
            await seating.release(workshop(starts_in=timedelta(hours=-1)), leaving)

        assert leaving.status == CONFIRMED


class TestFillFreeSeats:
    async def test_promotes_as_many_as_there_are_free_seats(self, seating, repo):
        w = workshop(capacity=5, seats_taken=2)
        waiting = [enrollment(id=n, attendee_id=n, status=WAITLISTED) for n in (1, 2)]
        repo.waitlist_head.return_value = waiting

        promoted = await seating.fill_free_seats(w)

        assert promoted == 2
        repo.waitlist_head.assert_awaited_once_with(w.id, 3)
        assert {e.status for e in waiting} == {CONFIRMED}
        assert w.seats_taken == 4

    async def test_a_full_workshop_promotes_nobody(self, seating, repo):
        w = workshop(capacity=2, seats_taken=2)

        assert await seating.fill_free_seats(w) == 0

        repo.waitlist_head.assert_not_called()
