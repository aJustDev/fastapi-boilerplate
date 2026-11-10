"""What each use case decides before anything is stored. Collaborators are mocked."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import AuthorizationError, BusinessValidationError, NotFoundError
from app.workshops.exceptions import (
    CapacityBelowEnrolledError,
    VersionConflictError,
    WorkshopRuleError,
)
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus
from app.workshops.use_cases.cancel_workshop import CancelWorkshopUseCase
from app.workshops.use_cases.leave_workshop import LeaveWorkshopUseCase
from app.workshops.use_cases.record_attendance import RecordAttendanceUseCase
from app.workshops.use_cases.send_reminders import SendRemindersUseCase
from app.workshops.use_cases.update_workshop import UpdateWorkshopUseCase
from tests._workshops import (
    MODERATOR,
    ORGANIZER,
    SOMEONE_ELSE,
    enrollment,
    workshop,
)

STARTED = timedelta(hours=-1)


def _workshops(found) -> AsyncMock:
    repo = AsyncMock()
    repo.get_for_update.return_value = found
    repo.get_by_id.return_value = found

    async def update(entity, data):
        for key, value in data.items():
            setattr(entity, key, value)
        return entity

    repo.update.side_effect = update
    return repo


class TestUpdateWorkshop:
    def _use_case(self, found) -> tuple[UpdateWorkshopUseCase, AsyncMock]:
        seating = AsyncMock()
        return UpdateWorkshopUseCase(_workshops(found), seating), seating

    async def test_applies_the_changes_and_counts_the_edit(self):
        w = workshop(version=3)
        use_case, seating = self._use_case(w)

        updated = await use_case.execute(w.id, 3, {"title": "New", "capacity": 5}, ORGANIZER)

        assert (updated.title, updated.capacity, updated.version) == ("New", 5, 4)
        seating.fill_free_seats.assert_awaited_once_with(w)

    async def test_a_version_that_is_no_longer_current_changes_nothing(self):
        w = workshop(version=3)
        use_case, _ = self._use_case(w)

        with pytest.raises(VersionConflictError) as refused:
            await use_case.execute(w.id, 2, {"title": "New"}, ORGANIZER)

        assert refused.value.code == "version_conflict"
        assert (w.title, w.version) == ("Intro to pottery", 3)

    async def test_capacity_cannot_go_below_the_seats_taken(self):
        w = workshop(capacity=5, seats_taken=3)
        use_case, _ = self._use_case(w)

        with pytest.raises(CapacityBelowEnrolledError):
            await use_case.execute(w.id, 1, {"capacity": 2}, ORGANIZER)

        assert w.capacity == 5
        await use_case.execute(w.id, 1, {"capacity": 3}, ORGANIZER)  # exactly the seats taken

    async def test_one_new_date_is_checked_against_the_stored_one(self):
        w = workshop()
        use_case, _ = self._use_case(w)

        with pytest.raises(BusinessValidationError):
            await use_case.execute(w.id, 1, {"ends_at": w.starts_at}, ORGANIZER)
        with pytest.raises(BusinessValidationError):
            await use_case.execute(w.id, 1, {"starts_at": w.ends_at}, ORGANIZER)

    @pytest.mark.parametrize("status", [WorkshopStatus.CANCELLED, WorkshopStatus.FINISHED])
    async def test_a_closed_workshop_is_not_edited(self, status):
        use_case, _ = self._use_case(workshop(status=status))

        with pytest.raises(WorkshopRuleError):
            await use_case.execute(10, 1, {"title": "New"}, ORGANIZER)

    async def test_only_who_runs_it_edits_it(self):
        use_case, _ = self._use_case(workshop())

        with pytest.raises(AuthorizationError):
            await use_case.execute(10, 1, {"title": "New"}, SOMEONE_ELSE)
        await use_case.execute(10, 1, {"title": "New"}, MODERATOR)


class TestCancelWorkshop:
    async def test_cancels_every_enrollment_and_tells_each_person(self):
        w = workshop(seats_taken=2)
        enrollments, bus = AsyncMock(), AsyncMock()
        enrollments.cancel_open.return_value = [(100, 2), (101, 3), (102, 4)]

        cancelled = await CancelWorkshopUseCase(_workshops(w), enrollments, bus).execute(
            w.id, ORGANIZER
        )

        assert (cancelled.status, cancelled.seats_taken) == (WorkshopStatus.CANCELLED, 0)
        event_type, events = bus.publish_many.call_args.args
        assert event_type == "enrollment.cancelled"
        assert [aggregate_id for aggregate_id, _ in events] == [100, 101, 102]
        assert [payload["attendee_id"] for _, payload in events] == [2, 3, 4]
        assert {payload["reason"] for _, payload in events} == {"workshop_cancelled"}

    async def test_a_cancelled_workshop_is_not_cancelled_again(self):
        enrollments, bus = AsyncMock(), AsyncMock()
        use_case = CancelWorkshopUseCase(
            _workshops(workshop(status=WorkshopStatus.CANCELLED)), enrollments, bus
        )

        with pytest.raises(WorkshopRuleError):
            await use_case.execute(10, ORGANIZER)

        enrollments.cancel_open.assert_not_called()
        bus.publish_many.assert_not_called()


class TestLeaveWorkshop:
    @pytest.mark.parametrize(
        "current",
        [None, enrollment(status=EnrollmentStatus.ATTENDED)],
        ids=["not-enrolled", "already-attended"],
    )
    async def test_there_is_nothing_to_leave(self, current):
        enrollments, seating = AsyncMock(), AsyncMock()
        enrollments.get_current.return_value = current
        use_case = LeaveWorkshopUseCase(_workshops(workshop()), enrollments, seating)

        with pytest.raises(NotFoundError):
            await use_case.execute(10, SOMEONE_ELSE)

        seating.release.assert_not_called()


class TestRecordAttendance:
    def _use_case(self, found_enrollment, **workshop_state) -> RecordAttendanceUseCase:
        enrollments = AsyncMock()
        enrollments.get_by_id.return_value = found_enrollment

        async def update(entity, data):
            for key, value in data.items():
                setattr(entity, key, value)
            return entity

        enrollments.update.side_effect = update
        w = workshop(**{"starts_in": STARTED} | workshop_state)
        return RecordAttendanceUseCase(_workshops(w), enrollments)

    @pytest.mark.parametrize(
        ("attended", "status"),
        [(True, EnrollmentStatus.ATTENDED), (False, EnrollmentStatus.NO_SHOW)],
    )
    async def test_records_the_answer(self, attended: bool, status):
        recorded = await self._use_case(enrollment()).execute(10, 100, attended, ORGANIZER)

        assert recorded.status == status

    async def test_recording_again_corrects_it(self):
        use_case = self._use_case(enrollment(status=EnrollmentStatus.NO_SHOW))

        recorded = await use_case.execute(10, 100, True, ORGANIZER)

        assert recorded.status == EnrollmentStatus.ATTENDED

    async def test_an_enrollment_of_another_workshop_is_not_reachable(self):
        # The permission was checked on workshop 10; enrollment 100 belongs to workshop 11.
        foreign = enrollment(workshop_id=11)

        with pytest.raises(NotFoundError):
            await self._use_case(foreign).execute(10, 100, True, ORGANIZER)

        assert foreign.status == EnrollmentStatus.CONFIRMED

    @pytest.mark.parametrize("status", [EnrollmentStatus.WAITLISTED, EnrollmentStatus.CANCELLED])
    async def test_someone_who_never_had_a_seat_has_no_attendance(self, status):
        with pytest.raises(WorkshopRuleError):
            await self._use_case(enrollment(status=status)).execute(10, 100, True, ORGANIZER)

    async def test_nothing_is_recorded_before_the_start(self):
        use_case = self._use_case(enrollment(), starts_in=timedelta(days=1))

        with pytest.raises(WorkshopRuleError):
            await use_case.execute(10, 100, True, ORGANIZER)

    async def test_only_who_runs_the_workshop_records_it(self):
        with pytest.raises(AuthorizationError):
            await self._use_case(enrollment()).execute(10, 100, True, SOMEONE_ELSE)


async def test_send_reminders_publishes_one_event_per_claimed_enrollment():
    from app.workshops.repos.enrollment import DueReminder

    w = workshop()
    enrollments, bus = AsyncMock(), AsyncMock()
    enrollments.claim_due_reminders.return_value = [
        DueReminder(100, w.id, 2, w.title, w.starts_at),
        DueReminder(101, w.id, 3, w.title, w.starts_at),
    ]
    bus.publish_many.side_effect = lambda _type, events: len(events)

    sent = await SendRemindersUseCase(enrollments, bus).execute()

    assert sent == 2
    event_type, events = bus.publish_many.call_args.args
    assert event_type == "enrollment.reminder"
    assert [aggregate_id for aggregate_id, _ in events] == [100, 101]
    assert events[0][1] == {
        "enrollment_id": 100,
        "workshop_id": w.id,
        "attendee_id": 2,
        "title": w.title,
        "starts_at": w.starts_at.isoformat(),
    }
