from datetime import datetime
from enum import StrEnum

from app.schemas.base import BaseSchema


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
    name: str
    description: str | None = None
    category: ItemCategory = ItemCategory.GENERAL
    priority: int = 0


class ItemUpdate(BaseSchema):
    name: str | None = None
    description: str | None = None
    category: ItemCategory | None = None
    priority: int | None = None
    is_active: bool | None = None


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
