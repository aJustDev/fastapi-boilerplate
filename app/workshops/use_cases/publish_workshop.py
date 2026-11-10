from dataclasses import dataclass

from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.schemas.workshop import WorkshopStatus
from app.workshops.services.access import Actor, ensure_runs
from app.workshops.services.lifecycle import move_to


@dataclass(slots=True)
class PublishWorkshopUseCase:
    workshop_repo: WorkshopRepo

    async def execute(self, workshop_id: int, actor: Actor) -> WorkshopORM:
        workshop = ensure_runs(
            await self.workshop_repo.get_for_update(workshop_id), workshop_id, actor
        )
        move_to(workshop, WorkshopStatus.PUBLISHED)
        return await self.workshop_repo.update(workshop, {})
