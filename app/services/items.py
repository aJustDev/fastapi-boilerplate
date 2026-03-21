import logging
from typing import Any

from app.core.exceptions import NotFoundError
from app.models.items.item import ItemORM
from app.repos.items.item import ItemRepo

logger = logging.getLogger(__name__)


class ItemService:
    def __init__(self, item_repo: ItemRepo):
        self.item_repo = item_repo

    async def create(
        self,
        name: str,
        owner_id: int,
        description: str | None = None,
        category: str = "general",
        priority: int = 0,
    ) -> ItemORM:
        item = ItemORM(
            name=name,
            description=description,
            category=category,
            priority=priority,
            owner_id=owner_id,
        )
        return await self.item_repo.create(item)

    async def get(self, item_id: int) -> ItemORM:
        item = await self.item_repo.get_by_id(item_id)
        if not item:
            raise NotFoundError("Item", item_id)
        return item

    async def update(self, item_id: int, data: dict[str, Any]) -> ItemORM:
        item = await self.get(item_id)
        return await self.item_repo.update(item, data)

    async def delete(self, item_id: int) -> None:
        item = await self.get(item_id)
        await self.item_repo.delete(item)

    async def list_paginated(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[ItemORM], int]:
        return await self.item_repo.list(
            page=page,
            page_size=page_size,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
        )

    async def get_filter_options(self) -> dict[str, list]:
        categories = await self.item_repo.get_distinct_categories()
        priorities = await self.item_repo.get_distinct_priorities()
        return {
            "category": categories,
            "priority": priorities,
            "is_active": [True, False],
        }

    async def list_cursor(
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
