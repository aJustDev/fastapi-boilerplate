from datetime import datetime
from enum import StrEnum

from pydantic import field_validator

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
    name: ShortText
    description: LongText | None = None
    category: ItemCategory = ItemCategory.GENERAL
    priority: Int32 = 0


class ItemUpdate(BaseSchema):
    """Partial update: a field that is absent is left as it is."""

    name: ShortText | None = None
    description: LongText | None = None
    category: ItemCategory | None = None
    priority: Int32 | None = None
    is_active: bool | None = None

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
    owner_id: int
    created_at: datetime
    updated_at: datetime | None


class ItemFilterOptions(BaseSchema):
    """Values present in the items the caller can see, to build filter controls."""

    category: list[str]
    priority: list[int]
    is_active: list[bool]
