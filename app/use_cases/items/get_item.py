from dataclasses import dataclass

from app.models.items.item import ItemORM
from app.services.items import ItemService


@dataclass(slots=True)
class GetItemUseCase:
    item_service: ItemService

    async def execute(self, item_id: int) -> ItemORM:
        return await self.item_service.get(item_id)
