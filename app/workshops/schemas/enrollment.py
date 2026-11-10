from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.core.schema import BaseSchema
from app.workshops.schemas.workshop import WorkshopSummary


class EnrollmentStatus(StrEnum):
    CONFIRMED = "confirmed"
    WAITLISTED = "waitlisted"
    CANCELLED = "cancelled"
    ATTENDED = "attended"
    NO_SHOW = "no_show"


class EnrollmentRead(BaseSchema):
    id: int
    workshop_id: int
    attendee_id: int = Field(description="Id of the enrolled user")
    status: EnrollmentStatus
    created_at: datetime = Field(
        description="When the user enrolled: the order of the waiting list"
    )
    updated_at: datetime | None = Field(description="`null` until the first change")


class MyEnrollmentRead(EnrollmentRead):
    workshop: WorkshopSummary


class AttendanceRecord(BaseSchema):
    attended: bool = Field(description="`false` records a no-show")
