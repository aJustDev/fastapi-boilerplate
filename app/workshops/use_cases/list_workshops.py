from dataclasses import dataclass
from typing import Any

from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.services.access import Actor, viewer_filter


@dataclass(slots=True)
class ListWorkshopsUseCase:
    workshop_repo: WorkshopRepo

    async def execute(
        self,
        actor: Actor,
        *,
        cursor: str | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[WorkshopORM], str | None, bool]:
        return await self.workshop_repo.list_visible(
            viewer_filter(actor),
            cursor=cursor,
            limit=limit,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
        )
