from dataclasses import dataclass

from app.core.events.bus import EventBus
from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.schemas.workshop import WorkshopStatus
from app.workshops.services.access import Actor, ensure_runs
from app.workshops.services.lifecycle import move_to
from app.workshops.services.seating import notice


@dataclass(slots=True)
class CancelWorkshopUseCase:
    workshop_repo: WorkshopRepo
    enrollment_repo: EnrollmentRepo
    event_bus: EventBus

    async def execute(self, workshop_id: int, actor: Actor) -> WorkshopORM:
        """Cancel the workshop and every enrollment in it, and tell each person.

        One transaction: the status, the enrollments and one event per attendee are
        stored together or not at all. The events are delivered afterwards by the outbox
        worker, each with its own retries, so a slow receiver does not hold the request.
        """
        workshop = ensure_runs(
            await self.workshop_repo.get_for_update(workshop_id), workshop_id, actor
        )
        move_to(workshop, WorkshopStatus.CANCELLED)
        cancelled = await self.enrollment_repo.cancel_open(workshop.id)
        await self.event_bus.publish_many(
            "enrollment.cancelled",
            [
                (
                    enrollment_id,
                    notice(workshop, enrollment_id, attendee_id, reason="workshop_cancelled"),
                )
                for enrollment_id, attendee_id in cancelled
            ],
        )
        return await self.workshop_repo.update(workshop, {"seats_taken": 0})
