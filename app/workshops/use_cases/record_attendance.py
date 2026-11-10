from dataclasses import dataclass

from app.core.exceptions import NotFoundError
from app.workshops.exceptions import WorkshopRuleError
from app.workshops.models.enrollment import EnrollmentORM
from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.services.access import Actor, ensure_runs
from app.workshops.services.lifecycle import ensure_started

# Who had a seat: the only enrollments attendance means something for.
_SEATED = (EnrollmentStatus.CONFIRMED, EnrollmentStatus.ATTENDED, EnrollmentStatus.NO_SHOW)


@dataclass(slots=True)
class RecordAttendanceUseCase:
    workshop_repo: WorkshopRepo
    enrollment_repo: EnrollmentRepo

    async def execute(
        self, workshop_id: int, enrollment_id: int, attended: bool, actor: Actor
    ) -> EnrollmentORM:
        """Record whether an attendee showed up. Recording again corrects the answer."""
        workshop = ensure_runs(
            await self.workshop_repo.get_for_update(workshop_id), workshop_id, actor
        )
        ensure_started(workshop)

        enrollment = await self.enrollment_repo.get_by_id(enrollment_id)
        # The permission was checked on the workshop of the path. An enrollment of another
        # workshop is not reachable through it, whatever its id.
        if enrollment is None or enrollment.workshop_id != workshop.id:
            raise NotFoundError("Enrollment", enrollment_id)
        if enrollment.status not in _SEATED:
            raise WorkshopRuleError(f"A {enrollment.status} enrollment has no attendance")

        status = EnrollmentStatus.ATTENDED if attended else EnrollmentStatus.NO_SHOW
        return await self.enrollment_repo.update(enrollment, {"status": status})
