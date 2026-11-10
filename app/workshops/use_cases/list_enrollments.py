from dataclasses import dataclass

from app.workshops.models.enrollment import EnrollmentORM
from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.services.access import Actor, ensure_runs


@dataclass(slots=True)
class ListWorkshopEnrollmentsUseCase:
    """Who enrolled in a workshop, for whoever runs it."""

    workshop_repo: WorkshopRepo
    enrollment_repo: EnrollmentRepo

    async def execute(
        self,
        workshop_id: int,
        actor: Actor,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[EnrollmentORM], int]:
        workshop = ensure_runs(await self.workshop_repo.get_by_id(workshop_id), workshop_id, actor)
        return await self.enrollment_repo.list_paginated(
            page=page,
            page_size=page_size,
            filters={"workshop_id": workshop.id, "status": status},
        )


@dataclass(slots=True)
class ListMyEnrollmentsUseCase:
    """The caller's own enrollments, each with its workshop."""

    enrollment_repo: EnrollmentRepo

    async def execute(
        self,
        actor: Actor,
        *,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> tuple[list[EnrollmentORM], int]:
        return await self.enrollment_repo.list_paginated(
            page=page,
            page_size=page_size,
            order_dir="desc",
            filters={"attendee_id": actor.user_id, "status": status},
        )
