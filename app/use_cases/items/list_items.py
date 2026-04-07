from dataclasses import dataclass
from typing import Any

from app.models.items.item import ItemORM
from app.repos.items.item import ItemRepo


@dataclass(slots=True)
class ListItemsUseCase:
    item_repo: ItemRepo

    async def execute(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ItemORM], int]:
        return await self.item_repo.list_paginated(
            page=page,
            page_size=page_size,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
        )


@dataclass(slots=True)
class ListItemsCursorUseCase:
    item_repo: ItemRepo

    async def execute(
        self,
        *,
        cursor: str | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ItemORM], str | None, bool]:
        return await self.item_repo.list_cursor(
            cursor=cursor,
            limit=limit,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
        )
