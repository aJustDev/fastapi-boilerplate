from datetime import datetime
from enum import StrEnum

from pydantic import Field, field_validator

from app.core.schema import BaseSchema, Int32, LongText, ShortText


class ItemCategory(StrEnum):
    ELECTRONICS = "electronics"
    FURNITURE = "furniture"
    BOOKS = "books"
    CLOTHING = "clothing"
    SPORTS = "sports"
    GENERAL = "general"


class ItemSortField(StrEnum):
    ID = "id"
    NAME = "name"
    CATEGORY = "category"
    PRIORITY = "priority"
    CREATED_AT = "created_at"


class ItemCreate(BaseSchema):
    name: ShortText = Field(description="1 to 200 characters", examples=["Desk lamp"])
    description: LongText | None = Field(default=None, description="Up to 10 000 characters")
    category: ItemCategory = Field(default=ItemCategory.GENERAL, description="One of the listed")
    priority: Int32 = Field(default=0, description="Any integer; lists can be sorted by it")


class ItemUpdate(BaseSchema):
    """Partial update: a field that is absent is left as it is."""

    name: ShortText | None = Field(default=None, description="1 to 200 characters")
    description: LongText | None = Field(
        default=None, description="Up to 10 000 characters; `null` clears it"
    )
    category: ItemCategory | None = Field(default=None, description="One of the listed")
    priority: Int32 | None = Field(default=None, description="Any integer")
    is_active: bool | None = Field(default=None, description="Inactive items stay listed")

    @field_validator("name", "category", "priority", "is_active", mode="before")
    @classmethod
    def _not_null(cls, value: object) -> object:
        # None is only the "absent" default of these fields. Sent explicitly it would
        # reach a NOT NULL column; `description` is nullable and may be cleared.
        if value is None:
            raise ValueError("null is not allowed; omit the field to leave it unchanged")
        return value


class ItemRead(BaseSchema):
    id: int
    name: str
    description: str | None
    category: str
    priority: int
    is_active: bool
    owner_id: int = Field(description="Id of the user who created it")
    created_at: datetime
    updated_at: datetime | None = Field(description="`null` until the first change")


class ItemFilterOptions(BaseSchema):
    """Values present in the items the caller can see, to build filter controls."""

    category: list[str]
    priority: list[int]
    is_active: list[bool]
