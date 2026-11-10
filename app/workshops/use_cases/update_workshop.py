from dataclasses import dataclass
from typing import Any

from app.core.exceptions import BusinessValidationError
from app.workshops.exceptions import CapacityBelowEnrolledError, VersionConflictError
from app.workshops.models.workshop import WorkshopORM
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.services.access import Actor, ensure_runs
from app.workshops.services.lifecycle import ensure_editable
from app.workshops.services.seating import SeatingService


@dataclass(slots=True)
class UpdateWorkshopUseCase:
    workshop_repo: WorkshopRepo
    seating: SeatingService

    async def execute(
        self, workshop_id: int, version: int, changes: dict[str, Any], actor: Actor
    ) -> WorkshopORM:
        """Apply the organizer's changes, if nobody changed the workshop in between.

        `version` is the one the client read. It is compared under the row lock, so of
        two edits that started from the same version exactly one is applied; the other
        gets 409 and has to read again instead of overwriting.
        """
        workshop = ensure_runs(
            await self.workshop_repo.get_for_update(workshop_id), workshop_id, actor
        )
        ensure_editable(workshop)
        if workshop.version != version:
            raise VersionConflictError(workshop.version)

        starts_at = changes.get("starts_at", workshop.starts_at)
        ends_at = changes.get("ends_at", workshop.ends_at)
        if ends_at <= starts_at:
            raise BusinessValidationError("ends_at must be after starts_at")
        if changes.get("capacity", workshop.capacity) < workshop.seats_taken:
            raise CapacityBelowEnrolledError(workshop.seats_taken)

        for field, value in changes.items():
            setattr(workshop, field, value)
        # More seats than before: they go to the people waiting, in order.
        await self.seating.fill_free_seats(workshop)
        return await self.workshop_repo.update(workshop, {"version": version + 1})
