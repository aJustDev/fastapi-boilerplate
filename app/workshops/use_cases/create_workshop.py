from dataclasses import dataclass
from datetime import datetime

from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.workshop import WorkshopRepo


@dataclass(slots=True)
class CreateWorkshopUseCase:
    workshop_repo: WorkshopRepo

    async def execute(
        self,
        organizer_id: int,
        *,
        title: str,
        description: str | None,
        starts_at: datetime,
        ends_at: datetime,
        capacity: int,
    ) -> WorkshopORM:
        """A new workshop starts as a draft: only its organizer sees it until published."""
        return await self.workshop_repo.create(
            WorkshopORM(
                organizer_id=organizer_id,
                title=title,
                description=description,
                starts_at=starts_at,
                ends_at=ends_at,
                capacity=capacity,
            )
        )
