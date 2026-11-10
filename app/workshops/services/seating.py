"""Who holds a seat and who waits.

The invariant: `workshop.seats_taken` equals the number of enrollments that hold a seat
(confirmed and, once the workshop took place, attended or no_show), never exceeds
`capacity`, and nobody waits while a seat is free.

It holds because every method here runs with the workshop row locked: they take a
`LockedWorkshop`, which only `WorkshopRepo.get_for_update` returns, so two requests about
the same workshop run one after the other. A lighter scheme, such as `UPDATE ... SET seats_taken = seats_taken + 1 WHERE
seats_taken < capacity`, protects the counter and not the waiting list: someone leaving
would not see a person who is being added to the list at that moment, and a seat would
stay free with people waiting. Requests about different workshops never wait for each
other.
"""

from dataclasses import dataclass
from typing import Any

from app.core.events.bus import EventBus
from app.workshops.models.enrollment import EnrollmentORM
from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.repos.workshop import LockedWorkshop
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.services.lifecycle import ensure_open_for_enrollment


def notice(workshop: WorkshopORM, enrollment_id: int, attendee_id: int, **extra: Any) -> dict:
    """Payload of an enrollment event: enough for the receiver to tell the attendee."""
    return {
        "enrollment_id": enrollment_id,
        "workshop_id": workshop.id,
        "attendee_id": attendee_id,
        "title": workshop.title,
        "starts_at": workshop.starts_at.isoformat(),
        **extra,
    }


@dataclass(slots=True)
class SeatingService:
    enrollment_repo: EnrollmentRepo
    event_bus: EventBus

    async def enroll(
        self, workshop: LockedWorkshop, attendee_id: int
    ) -> tuple[EnrollmentORM, bool]:
        """Enrol a user: a seat if one is free, the end of the waiting list otherwise.

        Returns the enrollment and whether this call created it. Enrolling twice returns
        the enrollment that exists, so a client may repeat a request it got no answer to.
        """
        current = await self.enrollment_repo.get_current(workshop.id, attendee_id)
        if current is not None:
            return current, False
        ensure_open_for_enrollment(workshop)

        has_seat = workshop.seats_taken < workshop.capacity
        enrollment = await self.enrollment_repo.create(
            EnrollmentORM(
                workshop_id=workshop.id,
                attendee_id=attendee_id,
                status=EnrollmentStatus.CONFIRMED if has_seat else EnrollmentStatus.WAITLISTED,
            )
        )
        if has_seat:
            workshop.seats_taken += 1
            await self.event_bus.publish(
                "enrollment.confirmed",
                notice(workshop, enrollment.id, attendee_id),
                aggregate_id=enrollment.id,
            )
        return enrollment, True

    async def release(self, workshop: LockedWorkshop, enrollment: EnrollmentORM) -> None:
        """End an enrollment at the attendee's request; a freed seat goes to who waits."""
        ensure_open_for_enrollment(workshop)
        held_a_seat = enrollment.status == EnrollmentStatus.CONFIRMED
        enrollment.status = EnrollmentStatus.CANCELLED
        await self.event_bus.publish(
            "enrollment.cancelled",
            notice(workshop, enrollment.id, enrollment.attendee_id, reason="left"),
            aggregate_id=enrollment.id,
        )
        if held_a_seat:
            workshop.seats_taken -= 1
            await self.fill_free_seats(workshop)

    async def fill_free_seats(self, workshop: LockedWorkshop) -> int:
        """Give the free seats to the head of the waiting list; returns how many."""
        free = workshop.capacity - workshop.seats_taken
        if free <= 0:
            return 0
        promoted = await self.enrollment_repo.waitlist_head(workshop.id, free)
        for enrollment in promoted:
            enrollment.status = EnrollmentStatus.CONFIRMED
        workshop.seats_taken += len(promoted)
        return await self.event_bus.publish_many(
            "enrollment.promoted",
            [(e.id, notice(workshop, e.id, e.attendee_id)) for e in promoted],
        )
