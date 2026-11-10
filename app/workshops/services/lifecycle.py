"""The states of a workshop and what each one allows.

    draft ──> published ──> finished
      │           │
      └───────────┴──> cancelled

`finished` is set by the workshops_finish job once the end has passed. Nothing leaves
`cancelled` or `finished`.
"""

from datetime import UTC, datetime

from app.workshops.exceptions import EnrollmentClosedError, WorkshopRuleError
from app.workshops.models.workshop import WorkshopORM
from app.workshops.schemas.workshop import WorkshopStatus

_NEXT: dict[str, frozenset[WorkshopStatus]] = {
    WorkshopStatus.DRAFT: frozenset({WorkshopStatus.PUBLISHED, WorkshopStatus.CANCELLED}),
    WorkshopStatus.PUBLISHED: frozenset({WorkshopStatus.CANCELLED, WorkshopStatus.FINISHED}),
    WorkshopStatus.CANCELLED: frozenset(),
    WorkshopStatus.FINISHED: frozenset(),
}


def move_to(workshop: WorkshopORM, target: WorkshopStatus) -> None:
    """Change the status, if the current one leads to `target`."""
    if target not in _NEXT[workshop.status]:
        raise WorkshopRuleError(f"A {workshop.status} workshop cannot become {target.value}")
    workshop.status = target


def ensure_editable(workshop: WorkshopORM) -> None:
    if not _NEXT[workshop.status]:
        raise WorkshopRuleError(f"A {workshop.status} workshop can no longer be changed")


def has_started(workshop: WorkshopORM) -> bool:
    return workshop.starts_at <= datetime.now(UTC)


def ensure_open_for_enrollment(workshop: WorkshopORM) -> None:
    """Enrolling and leaving stop when the workshop starts, is cancelled or was never published."""
    if workshop.status != WorkshopStatus.PUBLISHED or has_started(workshop):
        raise EnrollmentClosedError


def ensure_started(workshop: WorkshopORM) -> None:
    """Attendance is recorded once there is something to attend."""
    started = workshop.status == WorkshopStatus.FINISHED or (
        workshop.status == WorkshopStatus.PUBLISHED and has_started(workshop)
    )
    if not started:
        raise WorkshopRuleError("Attendance is recorded once the workshop has started")
