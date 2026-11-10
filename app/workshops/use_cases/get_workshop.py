from dataclasses import dataclass

from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.services.access import Actor, ensure_visible


@dataclass(slots=True)
class GetWorkshopUseCase:
    workshop_repo: WorkshopRepo

    async def execute(self, workshop_id: int, actor: Actor) -> WorkshopORM:
        return ensure_visible(await self.workshop_repo.get_by_id(workshop_id), workshop_id, actor)
