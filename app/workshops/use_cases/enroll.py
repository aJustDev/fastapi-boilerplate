from dataclasses import dataclass

from app.workshops.models.enrollment import EnrollmentORM
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.services.access import Actor, ensure_visible
from app.workshops.services.seating import SeatingService


@dataclass(slots=True)
class EnrollUseCase:
    workshop_repo: WorkshopRepo
    seating: SeatingService

    async def execute(self, workshop_id: int, actor: Actor) -> tuple[EnrollmentORM, bool]:
        """Enrol the caller. Returns the enrollment and whether this call created it."""
        workshop = ensure_visible(
            await self.workshop_repo.get_for_update(workshop_id), workshop_id, actor
        )
        return await self.seating.enroll(workshop, actor.user_id)
