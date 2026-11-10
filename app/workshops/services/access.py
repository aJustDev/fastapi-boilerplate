"""Who may act on which workshop.

Two checks, at two levels:
- the route requires a permission (`workshops:read`, `workshops:create`,
  `workshops:enroll`): what kind of thing the user may do at all (app/deps/auth.py,
  `require_permissions`);
- these rules decide on which workshops. A draft exists only for its organizer; once
  published, everyone sees it and only its organizer runs it. A holder of
  `workshops:moderate` sees and runs every workshop.
"""

from dataclasses import dataclass

from app.core.exceptions import AuthorizationError, NotFoundError
from app.workshops.models.workshop import WorkshopORM
from app.workshops.schemas.workshop import WorkshopStatus

MODERATE_PERMISSION = "workshops:moderate"


@dataclass(frozen=True, slots=True)
class Actor:
    """The user behind a request, reduced to what the workshop rules need."""

    user_id: int
    moderates: bool


def viewer_filter(actor: Actor) -> int | None:
    """The user a listing is limited to the view of; None means it sees everything."""
    return None if actor.moderates else actor.user_id


def _runs(workshop: WorkshopORM, actor: Actor) -> bool:
    return actor.moderates or workshop.organizer_id == actor.user_id


def ensure_visible[W: WorkshopORM](workshop: W | None, workshop_id: int, actor: Actor) -> W:
    """The workshop, if it exists and the actor may see it.

    Someone else's draft is reported as missing, with the same error as an id that does
    not exist: a 403 would tell the caller that the id is taken.
    """
    if workshop is None or (workshop.status == WorkshopStatus.DRAFT and not _runs(workshop, actor)):
        raise NotFoundError("Workshop", workshop_id)
    return workshop


def ensure_runs[W: WorkshopORM](workshop: W | None, workshop_id: int, actor: Actor) -> W:
    """The workshop, if the actor may change it, publish it, cancel it or see who enrolled.

    What the actor cannot see is missing (404). What it can see and does not run is
    forbidden (403): the workshop is public, so there is nothing to hide by lying.
    """
    workshop = ensure_visible(workshop, workshop_id, actor)
    if not _runs(workshop, actor):
        raise AuthorizationError("Only the organizer can do this")
    return workshop
