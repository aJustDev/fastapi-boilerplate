from dataclasses import dataclass

from app.core.exceptions import NotFoundError
from app.workshops.repos.enrollment import OPEN, EnrollmentRepo
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.services.access import Actor, ensure_visible
from app.workshops.services.seating import SeatingService


@dataclass(slots=True)
class LeaveWorkshopUseCase:
    workshop_repo: WorkshopRepo
    enrollment_repo: EnrollmentRepo
    seating: SeatingService

    async def execute(self, workshop_id: int, actor: Actor) -> None:
        """Cancel the caller's own enrollment; its seat goes to the first person waiting."""
        workshop = ensure_visible(
            await self.workshop_repo.get_for_update(workshop_id), workshop_id, actor
        )
        enrollment = await self.enrollment_repo.get_current(workshop.id, actor.user_id)
        if enrollment is None or enrollment.status not in OPEN:
            raise NotFoundError("Enrollment")
        await self.seating.release(workshop, enrollment)
