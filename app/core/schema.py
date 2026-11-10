from enum import StrEnum
from typing import Annotated

from fastapi import Path, Query
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Input types ───────────────────────────────────────────
# What a client sends ends up in a column: these types hold it to what the column and its
# indexes can take, so a value out of range is a 422 from validation and never an error
# raised by PostgreSQL or the driver. Request schemas use them instead of bare str and int.


def reject_nul(value: str) -> str:
    # PostgreSQL text cannot store U+0000; asyncpg fails the whole statement on it.
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


def _reject_nul_optional(value: str | None) -> str | None:
    return value if value is None else reject_nul(value)


ShortText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(reject_nul),
]
"""A name or a title: trimmed, not empty, short enough for a btree index."""

LongText = Annotated[str, StringConstraints(max_length=10_000), AfterValidator(reject_nul)]
"""Free text such as a description."""

Int32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]
"""A value stored in an INTEGER column."""

# Path and query parameters.
IdPath = Annotated[int, Path(ge=1, le=2**63 - 1)]
"""The id of a row: a BIGINT identity."""

PageQuery = Annotated[int, Query(ge=1, le=1_000_000)]
PageSizeQuery = Annotated[int, Query(ge=1, le=100)]
CursorQuery = Annotated[str | None, Query(max_length=1024)]
SearchQuery = Annotated[
    str | None, Query(min_length=1, max_length=200), AfterValidator(_reject_nul_optional)
]
"""A text filter."""


class SortDir(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaginatedResponse[T](BaseModel):
    """Classic offset-based pagination."""

    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return (self.total + self.page_size - 1) // self.page_size if self.page_size > 0 else 0


class CursorPaginatedResponse[T](BaseModel):
    """Cursor-based pagination for large datasets."""

    items: list[T]
    next_cursor: str | None = None
    has_more: bool = False
