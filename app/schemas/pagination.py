from enum import StrEnum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class SortDir(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaginatedResponse(BaseModel, Generic[T]):
    """Classic offset-based pagination."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size > 0 else 0


class CursorPaginatedResponse(BaseModel, Generic[T]):
    """Cursor-based pagination for large datasets."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
