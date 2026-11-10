from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from app.core.schema import BaseSchema, Int32, LongText, ShortText, Timestamp


class WorkshopStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CANCELLED = "cancelled"
    FINISHED = "finished"


class WorkshopSortField(StrEnum):
    STARTS_AT = "starts_at"
    CREATED_AT = "created_at"
    ID = "id"


Capacity = Annotated[int, Field(ge=1, le=10_000)]
"""Seats of a workshop."""


class WorkshopCreate(BaseSchema):
    title: ShortText = Field(description="1 to 200 characters", examples=["Intro to pottery"])
    description: LongText | None = Field(default=None, description="Up to 10 000 characters")
    starts_at: Timestamp = Field(description="With its UTC offset", examples=["2030-05-04T10:00Z"])
    ends_at: Timestamp = Field(description="After `starts_at`", examples=["2030-05-04T12:00Z"])
    capacity: Capacity = Field(description="Seats: 1 to 10 000", examples=[12])

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class WorkshopUpdate(BaseSchema):
    """Partial update: a field that is absent is left as it is."""

    version: Int32 = Field(
        description="The `version` the client read; 409 `version_conflict` if it changed since"
    )
    title: ShortText | None = Field(default=None, description="1 to 200 characters")
    description: LongText | None = Field(
        default=None, description="Up to 10 000 characters; `null` clears it"
    )
    starts_at: Timestamp | None = Field(default=None, description="With its UTC offset")
    ends_at: Timestamp | None = Field(default=None, description="After `starts_at`")
    capacity: Capacity | None = Field(
        default=None,
        description="Not below the seats taken; more seats go to the waiting list in order",
    )

    @field_validator("title", "starts_at", "ends_at", "capacity", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # None is only the "absent" default of these fields. Sent explicitly it would
        # reach a NOT NULL column; `description` is nullable and may be cleared.
        if value is None:
            raise ValueError("null is not allowed; omit the field to leave it unchanged")
        return value


class WorkshopRead(BaseSchema):
    id: int
    organizer_id: int = Field(description="Id of the user who created it")
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    capacity: int
    seats_taken: int = Field(description="Enrollments that hold a seat; the rest wait in order")
    status: WorkshopStatus
    version: int = Field(description="Send it back in a PATCH")
    created_at: datetime
    updated_at: datetime | None = Field(description="`null` until the first change")


class WorkshopSummary(BaseSchema):
    """What an enrollment shows of its workshop."""

    id: int
    title: str
    starts_at: datetime
    ends_at: datetime
    status: WorkshopStatus
