from dataclasses import dataclass
from typing import Any

from app.models.items.item import ItemORM
from app.services.items import ItemService


@dataclass(slots=True)
class UpdateItemUseCase:
    item_service: ItemService

    async def execute(self, item_id: int, data: dict[str, Any]) -> ItemORM:
        return await self.item_service.update(item_id, data)
