from dataclasses import dataclass
from typing import Any

from app.items.models.item import ItemORM
from app.items.repos.item import ItemRepo
from app.items.services.access import Actor, owner_filter


def _scoped(filters: dict[str, Any] | None, actor: Actor) -> dict[str, Any]:
    """The filters of the request plus the owner the actor is limited to."""
    # After the client's filters, so nothing sent by the client can widen the scope.
    return {**(filters or {}), "owner_id": owner_filter(actor)}


@dataclass(slots=True)
class ListItemsUseCase:
    item_repo: ItemRepo

    async def execute(
        self,
        actor: Actor,
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
            filters=_scoped(filters, actor),
        )


@dataclass(slots=True)
class ListItemsCursorUseCase:
    item_repo: ItemRepo

    async def execute(
        self,
        actor: Actor,
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
            filters=_scoped(filters, actor),
        )
