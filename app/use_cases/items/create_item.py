from dataclasses import dataclass

from app.models.items.item import ItemORM
from app.services.items import ItemService


@dataclass(slots=True)
class CreateItemUseCase:
    item_service: ItemService

    async def execute(
        self,
        name: str,
        owner_id: int,
        description: str | None = None,
        category: str = "general",
        priority: int = 0,
    ) -> ItemORM:
        return await self.item_service.create(name, owner_id, description, category, priority)
