import base64
import json
import logging
from typing import Any, Literal, TypedDict

from pydantic import TypeAdapter, ValidationError
from pydantic_core import to_jsonable_python
from sqlalchemy import ColumnElement, Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base
from app.core.exceptions import InvalidCursorError

logger = logging.getLogger(__name__)

FilterOp = Literal["eq", "ilike", "gte", "lte"]


class FieldMapping(TypedDict):
    column: Any
    op: FilterOp


_MAX_ID = 2**63 - 1


def encode_cursor(values: dict[str, Any]) -> str:
    # JSON mode: a datetime leaves as ISO 8601, which `_cursor_value` reads back.
    payload = json.dumps(to_jsonable_python(values))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    """The values of a cursor issued by `encode_cursor`.

    A cursor is client input: anything that is not base64 of a JSON object with an
    integer `id` raises InvalidCursorError instead of failing somewhere below.
    """
    try:
        decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except ValueError as e:  # bad base64, bad UTF-8 and bad JSON are all ValueError
        raise InvalidCursorError from e
    if not isinstance(decoded, dict):
        raise InvalidCursorError
    cursor_id = decoded.get("id")
    if type(cursor_id) is not int or not 1 <= cursor_id <= _MAX_ID:
        raise InvalidCursorError
    return decoded


def _like_literal(value: str) -> str:
    """`value` escaped so that LIKE matches its characters, not its wildcards."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _cursor_value(column: Any, raw: Any) -> Any:
    """The sort value of a cursor, back in the Python type of its column.

    JSON has no datetime (or Decimal, or UUID): the value travels as a string and has to
    be compared with the column as what it was. A value of another type is a forged cursor.
    """
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return raw
    try:
        return TypeAdapter(python_type).validate_python(raw)
    except ValidationError as e:
        raise InvalidCursorError from e


class BaseRepo[T: Base]:
    """Async generic repository with offset and cursor pagination."""

    model: type[T]
    map_field: dict[str, FieldMapping] = {}

    def __init__(self, session: AsyncSession):
        self.session = session

    @property
    def _pk(self) -> Any:
        """The model's `id` column. Base does not declare it; IntPkMixin models do."""
        return self.model.id  # type: ignore[attr-defined]

    def _base_select(self) -> Select:
        return select(self.model)

    # ── CRUD ──────────────────────────────────────────────

    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: int) -> T | None:
        stmt = self._base_select().where(self._pk == entity_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def update(self, entity: T, data: dict[str, Any]) -> T:
        for key, value in data.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def delete(self, entity: T) -> None:
        await self.session.delete(entity)
        await self.session.flush()

    # ── Offset pagination ─────────────────────────────────

    async def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
        scope: ColumnElement[bool] | None = None,
    ) -> tuple[list[T], int]:
        """Returns (items, total). `filters` and `scope` are described in `_matching`."""
        stmt = self._matching(filters, scope)
        stmt = self._apply_ordering(stmt, order_by, order_dir)

        offset = (page - 1) * page_size
        stmt = stmt.add_columns(func.count().over().label("_total_count"))
        stmt = stmt.offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            # The total travels on the rows, and this page has none. On the first page
            # that means zero matches; past the last one the client still wants the count.
            return [], 0 if page == 1 else await self._count(filters, scope)

        items = [row[0] for row in rows]
        total = rows[0]._total_count

        return items, total

    async def _count(
        self, filters: dict[str, Any] | None, scope: ColumnElement[bool] | None = None
    ) -> int:
        matching = self._matching(filters, scope).subquery()
        result = await self.session.execute(select(func.count()).select_from(matching))
        return int(result.scalar_one())

    def _matching(
        self, filters: dict[str, Any] | None, scope: ColumnElement[bool] | None
    ) -> Select:
        """The rows a listing is about.

        `filters` is what the client asked for: keys declared in `map_field`, anything
        else ignored. `scope` is what the caller may see at all (its own rows, the
        published ones, a tenant): a condition written by the repository, which no query
        parameter can widen.
        """
        stmt = self._apply_filters(self._base_select(), filters)
        return stmt if scope is None else stmt.where(scope)

    # ── Cursor pagination ─────────────────────────────────

    async def list_cursor(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
        scope: ColumnElement[bool] | None = None,
    ) -> tuple[list[T], str | None, bool]:
        """Returns (items, next_cursor, has_more).

        Supports sorting by any mapped/model field with id as tiebreaker.
        Cursor is a base64-encoded JSON with the sort field value and id.
        """
        sort_column, sort_field, direction = self._resolve_sort(order_by, order_dir)

        stmt = self._matching(filters, scope)

        if cursor is not None:
            cursor_data = decode_cursor(cursor)
            stmt = self._apply_cursor_where(stmt, cursor_data, sort_column, sort_field, direction)

        # Apply ordering: sort field + id tiebreaker
        if sort_field != "id":
            stmt = stmt.order_by(direction(sort_column), direction(self._pk))
        else:
            stmt = stmt.order_by(direction(self._pk))

        stmt = stmt.limit(limit + 1)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        has_more = len(items) > limit
        if has_more:
            items = items[:limit]

        next_cursor = None
        if items and has_more:
            last = items[-1]
            cursor_values = {"id": last.id}
            if sort_field != "id":
                cursor_values[sort_field] = getattr(last, sort_field)
            next_cursor = encode_cursor(cursor_values)

        return items, next_cursor, has_more

    # ── Filtering & ordering ──────────────────────────────

    def _resolve_sort(self, order_by: str | None, order_dir: str) -> tuple[Any, str, Any]:
        """Returns (column, field_name, direction_func)."""
        direction = desc if order_dir.lower() == "desc" else asc

        if not order_by or order_by == "id":
            return self._pk, "id", direction

        field_config = self.map_field.get(order_by)
        if field_config:
            return field_config["column"], order_by, direction

        if hasattr(self.model, order_by):
            return getattr(self.model, order_by), order_by, direction

        return self._pk, "id", direction

    def _apply_cursor_where(
        self,
        stmt: Select,
        cursor_data: dict[str, Any],
        sort_column: Any,
        sort_field: str,
        direction: Any,
    ) -> Select:
        """Applies WHERE clause for cursor-based pagination.

        For composite sort (field + id tiebreaker), uses:
          (field > val) OR (field = val AND id > cursor_id)   -- asc
          (field < val) OR (field = val AND id < cursor_id)   -- desc
        """
        cursor_id = cursor_data["id"]

        if sort_field == "id":
            if direction is asc:
                return stmt.where(self._pk > cursor_id)
            return stmt.where(self._pk < cursor_id)

        if sort_field not in cursor_data:
            # Issued for another order: paging on with it would skip or repeat rows.
            raise InvalidCursorError
        cursor_value = _cursor_value(sort_column, cursor_data[sort_field])

        if direction is asc:
            return stmt.where(
                (sort_column > cursor_value)
                | ((sort_column == cursor_value) & (self._pk > cursor_id))
            )
        return stmt.where(
            (sort_column < cursor_value) | ((sort_column == cursor_value) & (self._pk < cursor_id))
        )

    def _apply_filters(self, stmt: Select, filters: dict[str, Any] | None) -> Select:
        if not filters:
            return stmt
        for key, value in filters.items():
            if value is None:
                continue
            field_config = self.map_field.get(key)
            if not field_config:
                # Only what the repository declares in `map_field` is a filter: a model
                # attribute that happens to share the name of a key is not an invitation.
                logger.warning("Unknown filter field ignored: %s", key)
                continue
            column = field_config["column"]
            op = field_config["op"]
            if op == "eq":
                stmt = stmt.where(column == value)
            elif op == "ilike":
                stmt = stmt.where(column.ilike(f"%{_like_literal(str(value))}%", escape="\\"))
            elif op == "gte":
                stmt = stmt.where(column >= value)
            elif op == "lte":
                stmt = stmt.where(column <= value)
        return stmt

    def _apply_ordering(self, stmt: Select, order_by: str | None, order_dir: str) -> Select:
        sort_column, sort_field, direction = self._resolve_sort(order_by, order_dir)
        if sort_field == "id":
            return stmt.order_by(direction(self._pk))
        # The id breaks the ties. Without it PostgreSQL may return rows with the same sort
        # value in a different order for each OFFSET, and pages repeat and skip rows.
        return stmt.order_by(direction(sort_column), direction(self._pk))
