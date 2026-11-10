from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.core.config import settings
from app.core.events.bus import EventBus
from app.core.exceptions.schemas import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    RATE_LIMITED,
    UNAUTHENTICATED,
)
from app.core.ratelimit import limiter
from app.core.schema import (
    CursorPaginatedResponse,
    CursorQuery,
    IdPath,
    PageQuery,
    PageSizeQuery,
    PaginatedResponse,
    SearchQuery,
    SortDir,
    Timestamp,
)
from app.deps.auth import User, require_permissions
from app.deps.events import get_event_bus
from app.deps.repository import get_repo
from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.repos.workshop import WorkshopRepo
from app.workshops.schemas.enrollment import (
    AttendanceRecord,
    EnrollmentRead,
    EnrollmentStatus,
    MyEnrollmentRead,
)
from app.workshops.schemas.workshop import (
    WorkshopCreate,
    WorkshopRead,
    WorkshopSortField,
    WorkshopStatus,
    WorkshopUpdate,
)
from app.workshops.services.access import MODERATE_PERMISSION, Actor
from app.workshops.services.seating import SeatingService
from app.workshops.use_cases.cancel_workshop import CancelWorkshopUseCase
from app.workshops.use_cases.create_workshop import CreateWorkshopUseCase
from app.workshops.use_cases.enroll import EnrollUseCase
from app.workshops.use_cases.get_workshop import GetWorkshopUseCase
from app.workshops.use_cases.leave_workshop import LeaveWorkshopUseCase
from app.workshops.use_cases.list_enrollments import (
    ListMyEnrollmentsUseCase,
    ListWorkshopEnrollmentsUseCase,
)
from app.workshops.use_cases.list_workshops import ListWorkshopsUseCase
from app.workshops.use_cases.publish_workshop import PublishWorkshopUseCase
from app.workshops.use_cases.record_attendance import RecordAttendanceUseCase
from app.workshops.use_cases.update_workshop import UpdateWorkshopUseCase

_ERRORS = {**UNAUTHENTICATED, **FORBIDDEN, **RATE_LIMITED}

router = APIRouter(prefix="/workshops", tags=["Workshops"], responses=_ERRORS)
# What belongs to the caller, addressed without an id.
me_router = APIRouter(prefix="/me", tags=["Workshops"], responses=_ERRORS)

WorkshopRepoDep = Annotated[WorkshopRepo, Depends(get_repo(WorkshopRepo))]
EnrollmentRepoDep = Annotated[EnrollmentRepo, Depends(get_repo(EnrollmentRepo))]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


def _seating(enrollments: EnrollmentRepoDep, event_bus: EventBusDep) -> SeatingService:
    return SeatingService(enrollments, event_bus)


Seating = Annotated[SeatingService, Depends(_seating)]


def _actor_with(permission: str) -> Callable[..., Awaitable[Actor]]:
    """Dependency: the caller, who must hold `permission` (403 otherwise), as an Actor.

    The permission answers "may this user do this kind of thing"; which workshops it
    applies to is decided by the use case with the Actor (app/workshops/services/access.py).
    """

    async def _actor(
        user: Annotated[User, Depends(require_permissions(permission=permission))],
    ) -> Actor:
        return Actor(user_id=user.id, moderates=user.has_permission(MODERATE_PERMISSION))

    return _actor


Viewer = Annotated[Actor, Depends(_actor_with("workshops:read"))]
Organizer = Annotated[Actor, Depends(_actor_with("workshops:create"))]
Attendee = Annotated[Actor, Depends(_actor_with("workshops:enroll"))]


# ── Workshops ─────────────────────────────────────────────


@router.post("", response_model=WorkshopRead, status_code=201)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def create_workshop(
    request: Request, body: WorkshopCreate, repo: WorkshopRepoDep, actor: Organizer
):
    """Create a workshop organized by the caller. It starts as a draft, visible to nobody else."""
    uc = CreateWorkshopUseCase(repo)
    workshop = await uc.execute(actor.user_id, **body.model_dump())
    return WorkshopRead.model_validate(workshop)


@router.get("", response_model=CursorPaginatedResponse[WorkshopRead], responses={**BAD_REQUEST})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_workshops(
    request: Request,
    repo: WorkshopRepoDep,
    actor: Viewer,
    cursor: CursorQuery = None,
    limit: PageSizeQuery = 20,
    order_by: WorkshopSortField = WorkshopSortField.STARTS_AT,
    order_dir: SortDir = SortDir.ASC,
    status: WorkshopStatus | None = None,
    starts_after: Timestamp | None = None,
    q: SearchQuery = None,
):
    """Workshops by cursor: pass `next_cursor` of a page to get the next one.

    Everyone sees the workshops that were published; a draft is listed only to its
    organizer. `q` is a "contains" filter on the title. Keep `order_by` and the filters
    the same between pages; a cursor issued for another order answers 400 `invalid_cursor`.
    """
    uc = ListWorkshopsUseCase(repo)
    workshops, next_cursor, has_more = await uc.execute(
        actor,
        cursor=cursor,
        limit=limit,
        order_by=order_by.value,
        order_dir=order_dir.value,
        filters={"status": status, "starts_after": starts_after, "title": q},
    )
    return CursorPaginatedResponse(
        items=[WorkshopRead.model_validate(w) for w in workshops],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{workshop_id}", response_model=WorkshopRead, responses={**NOT_FOUND})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_workshop(request: Request, workshop_id: IdPath, repo: WorkshopRepoDep, actor: Viewer):
    """One workshop. 404 also for a draft that belongs to someone else."""
    uc = GetWorkshopUseCase(repo)
    workshop = await uc.execute(workshop_id, actor)
    return WorkshopRead.model_validate(workshop)


@router.patch(
    "/{workshop_id}",
    response_model=WorkshopRead,
    responses={**BAD_REQUEST, **NOT_FOUND, **CONFLICT},
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def update_workshop(
    request: Request,
    workshop_id: IdPath,
    body: WorkshopUpdate,
    repo: WorkshopRepoDep,
    seating: Seating,
    actor: Organizer,
):
    """Change the fields sent, for the organizer. `version` must be the one last read.

    409 `version_conflict` if the workshop changed since, `capacity_below_enrolled` if
    the new capacity does not fit the seats taken, `invalid_state` once it is cancelled
    or finished. Raising the capacity confirms the first people of the waiting list.
    """
    uc = UpdateWorkshopUseCase(repo, seating)
    changes = body.model_dump(exclude_unset=True, exclude={"version"})
    workshop = await uc.execute(workshop_id, body.version, changes, actor)
    return WorkshopRead.model_validate(workshop)


@router.post(
    "/{workshop_id}/publish", response_model=WorkshopRead, responses={**NOT_FOUND, **CONFLICT}
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def publish_workshop(
    request: Request, workshop_id: IdPath, repo: WorkshopRepoDep, actor: Organizer
):
    """Open a draft to everyone: it is listed and people can enrol. 409 if it is not a draft."""
    uc = PublishWorkshopUseCase(repo)
    workshop = await uc.execute(workshop_id, actor)
    return WorkshopRead.model_validate(workshop)


@router.post(
    "/{workshop_id}/cancel", response_model=WorkshopRead, responses={**NOT_FOUND, **CONFLICT}
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def cancel_workshop(
    request: Request,
    workshop_id: IdPath,
    repo: WorkshopRepoDep,
    enrollments: EnrollmentRepoDep,
    event_bus: EventBusDep,
    actor: Organizer,
):
    """Cancel a workshop and every enrollment in it.

    Publishes one `enrollment.cancelled` per person enrolled or waiting. 409 if it was
    already cancelled or has finished.
    """
    uc = CancelWorkshopUseCase(repo, enrollments, event_bus)
    workshop = await uc.execute(workshop_id, actor)
    return WorkshopRead.model_validate(workshop)


# ── Enrollments ───────────────────────────────────────────


@router.post(
    "/{workshop_id}/enrollments",
    response_model=EnrollmentRead,
    status_code=201,
    responses={
        200: {"model": EnrollmentRead, "description": "Already enrolled: the enrollment as it is"},
        **NOT_FOUND,
        **CONFLICT,
    },
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def enroll(
    request: Request,
    response: Response,
    workshop_id: IdPath,
    repo: WorkshopRepoDep,
    seating: Seating,
    actor: Attendee,
):
    """Enrol the caller: `confirmed` if a seat is free, `waitlisted` otherwise.

    Safe to repeat: a second call answers 200 with the same enrollment. Publishes
    `enrollment.confirmed`. 409 `enrollment_closed` unless the workshop is published and
    has not started.
    """
    uc = EnrollUseCase(repo, seating)
    enrollment, created = await uc.execute(workshop_id, actor)
    if not created:
        response.status_code = 200
    return EnrollmentRead.model_validate(enrollment)


@router.delete(
    "/{workshop_id}/enrollments/me", status_code=204, responses={**NOT_FOUND, **CONFLICT}
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def leave_workshop(
    request: Request,
    workshop_id: IdPath,
    repo: WorkshopRepoDep,
    enrollments: EnrollmentRepoDep,
    seating: Seating,
    actor: Attendee,
):
    """Cancel the caller's enrollment. A freed seat goes to the first person waiting.

    Publishes `enrollment.cancelled`, and `enrollment.promoted` for whoever gets the
    seat. 404 if the caller is not enrolled, 409 `enrollment_closed` once it has started.
    """
    uc = LeaveWorkshopUseCase(repo, enrollments, seating)
    await uc.execute(workshop_id, actor)


@router.get(
    "/{workshop_id}/enrollments",
    response_model=PaginatedResponse[EnrollmentRead],
    responses={**NOT_FOUND},
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_workshop_enrollments(
    request: Request,
    workshop_id: IdPath,
    repo: WorkshopRepoDep,
    enrollments: EnrollmentRepoDep,
    actor: Organizer,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    status: EnrollmentStatus | None = None,
):
    """Who enrolled, in order, for the organizer. The waiting list is `status=waitlisted`."""
    uc = ListWorkshopEnrollmentsUseCase(repo, enrollments)
    found, total = await uc.execute(
        workshop_id, actor, page=page, page_size=page_size, status=status
    )
    return PaginatedResponse(
        items=[EnrollmentRead.model_validate(e) for e in found],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/{workshop_id}/enrollments/{enrollment_id}/attendance",
    response_model=EnrollmentRead,
    responses={**NOT_FOUND, **CONFLICT},
)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def record_attendance(
    request: Request,
    workshop_id: IdPath,
    enrollment_id: IdPath,
    body: AttendanceRecord,
    repo: WorkshopRepoDep,
    enrollments: EnrollmentRepoDep,
    actor: Organizer,
):
    """Record whether an attendee showed up, for the organizer, once the workshop started.

    404 for an enrollment that is not of this workshop. 409 `invalid_state` before the
    start, or for someone who never had a seat.
    """
    uc = RecordAttendanceUseCase(repo, enrollments)
    enrollment = await uc.execute(workshop_id, enrollment_id, body.attended, actor)
    return EnrollmentRead.model_validate(enrollment)


@me_router.get("/enrollments", response_model=PaginatedResponse[MyEnrollmentRead])
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_my_enrollments(
    request: Request,
    enrollments: EnrollmentRepoDep,
    actor: Attendee,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    status: EnrollmentStatus | None = None,
):
    """The caller's enrollments, newest first, each with its workshop."""
    uc = ListMyEnrollmentsUseCase(enrollments)
    found, total = await uc.execute(actor, page=page, page_size=page_size, status=status)
    return PaginatedResponse(
        items=[MyEnrollmentRead.model_validate(e) for e in found],
        total=total,
        page=page,
        page_size=page_size,
    )
