import base64
import json
import logging
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import Base

T = TypeVar("T", bound=Base)

logger = logging.getLogger(__name__)


def encode_cursor(values: dict[str, Any]) -> str:
    payload = json.dumps(values, default=str)
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str) -> dict[str, Any]:
    payload = base64.urlsafe_b64decode(cursor.encode()).decode()
    return json.loads(payload)


class BaseRepo(Generic[T]):
    """Async generic repository with offset and cursor pagination."""

    model: type[T]
    map_field: dict[str, dict[str, Any]] = {}

    def __init__(self, session: AsyncSession):
        self.session = session

    def _base_select(self) -> Select:
        return select(self.model)

    # ── CRUD ──────────────────────────────────────────────

    async def create(self, entity: T) -> T:
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: int) -> T | None:
        stmt = self._base_select().where(self.model.id == entity_id)
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
    ) -> tuple[list[T], int]:
        stmt = self._base_select()
        stmt = self._apply_filters(stmt, filters)
        stmt = self._apply_ordering(stmt, order_by, order_dir)

        offset = (page - 1) * page_size
        stmt = stmt.add_columns(func.count().over().label("_total_count"))
        stmt = stmt.offset(offset).limit(page_size)
        result = await self.session.execute(stmt)
        rows = result.all()

        if not rows:
            return [], 0

        items = [row[0] for row in rows]
        total = rows[0]._total_count

        return items, total

    # ── Cursor pagination ─────────────────────────────────

    async def list_cursor(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[T], str | None, bool]:
        """Returns (items, next_cursor, has_more).

        Supports sorting by any mapped/model field with id as tiebreaker.
        Cursor is a base64-encoded JSON with the sort field value and id.
        """
        sort_column, sort_field, direction = self._resolve_sort(order_by, order_dir)

        stmt = self._base_select()
        stmt = self._apply_filters(stmt, filters)

        if cursor is not None:
            cursor_data = decode_cursor(cursor)
            stmt = self._apply_cursor_where(stmt, cursor_data, sort_column, sort_field, direction)

        # Apply ordering: sort field + id tiebreaker
        if sort_field != "id":
            stmt = stmt.order_by(direction(sort_column), direction(self.model.id))
        else:
            stmt = stmt.order_by(direction(self.model.id))

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
            return self.model.id, "id", direction

        field_config = self.map_field.get(order_by)
        if field_config:
            return field_config["column"], order_by, direction

        if hasattr(self.model, order_by):
            return getattr(self.model, order_by), order_by, direction

        return self.model.id, "id", direction

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
                return stmt.where(self.model.id > cursor_id)
            return stmt.where(self.model.id < cursor_id)

        cursor_value = cursor_data.get(sort_field)

        if direction is asc:
            return stmt.where(
                (sort_column > cursor_value)
                | ((sort_column == cursor_value) & (self.model.id > cursor_id))
            )
        return stmt.where(
            (sort_column < cursor_value)
            | ((sort_column == cursor_value) & (self.model.id < cursor_id))
        )

    def _apply_filters(self, stmt: Select, filters: dict[str, Any] | None) -> Select:
        if not filters:
            return stmt
        for key, value in filters.items():
            if value is None:
                continue
            field_config = self.map_field.get(key)
            if field_config:
                column = field_config["column"]
                op = field_config.get("op", "eq")
                if op == "eq":
                    stmt = stmt.where(column == value)
                elif op == "ilike":
                    stmt = stmt.where(column.ilike(f"%{value}%"))
                elif op == "gte":
                    stmt = stmt.where(column >= value)
                elif op == "lte":
                    stmt = stmt.where(column <= value)
            elif hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)
            else:
                logger.warning("Unknown filter field ignored: %s", key)
        return stmt

    def _apply_ordering(self, stmt: Select, order_by: str | None, order_dir: str) -> Select:
        if not order_by:
            return stmt.order_by(asc(self.model.id))

        field_config = self.map_field.get(order_by)
        if field_config:
            column = field_config["column"]
        elif hasattr(self.model, order_by):
            column = getattr(self.model, order_by)
        else:
            return stmt.order_by(asc(self.model.id))

        direction = desc if order_dir.lower() == "desc" else asc
        return stmt.order_by(direction(column))
