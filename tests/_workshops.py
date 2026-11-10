"""Valid workshops and enrollments, for the tests that need one without caring what is in it:
as the body of a request, or as objects in memory for tests that never reach a database."""

from datetime import UTC, datetime, timedelta
from typing import Any

from app.workshops.models.enrollment import EnrollmentORM
from app.workshops.models.workshop import WorkshopORM
from app.workshops.schemas.enrollment import EnrollmentStatus
from app.workshops.schemas.workshop import WorkshopStatus
from app.workshops.services.access import Actor


def workshop_body(*, starts_in: timedelta = timedelta(days=7), **overrides: Any) -> dict[str, Any]:
    """Body of `POST /v1/workshops`: two hours long, starting `starts_in` from now."""
    starts_at = datetime.now(UTC) + starts_in
    body: dict[str, Any] = {
        "title": "Intro to pottery",
        "starts_at": starts_at.isoformat(),
        "ends_at": (starts_at + timedelta(hours=2)).isoformat(),
        "capacity": 2,
    }
    return {**body, **overrides}


ORGANIZER = Actor(user_id=1, moderates=False)
SOMEONE_ELSE = Actor(user_id=2, moderates=False)
MODERATOR = Actor(user_id=99, moderates=True)


def workshop(*, starts_in: timedelta = timedelta(days=7), **overrides: Any) -> WorkshopORM:
    """A published workshop of ORGANIZER with 2 seats, none taken."""
    starts_at = datetime.now(UTC) + starts_in
    values: dict[str, Any] = {
        "id": 10,
        "organizer_id": ORGANIZER.user_id,
        "title": "Intro to pottery",
        "description": None,
        "starts_at": starts_at,
        "ends_at": starts_at + timedelta(hours=2),
        "capacity": 2,
        "seats_taken": 0,
        "status": WorkshopStatus.PUBLISHED,
        "version": 1,
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }
    return WorkshopORM(**values | overrides)


def enrollment(**overrides: Any) -> EnrollmentORM:
    """A confirmed enrollment of user 2 in workshop 10."""
    values: dict[str, Any] = {
        "id": 100,
        "workshop_id": 10,
        "attendee_id": SOMEONE_ELSE.user_id,
        "status": EnrollmentStatus.CONFIRMED,
        "created_at": datetime.now(UTC),
        "updated_at": None,
    }
    return EnrollmentORM(**values | overrides)
