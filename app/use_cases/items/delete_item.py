from dataclasses import dataclass

from app.services.items import ItemService


@dataclass(slots=True)
class DeleteItemUseCase:
    item_service: ItemService

    async def execute(self, item_id: int) -> None:
        await self.item_service.delete(item_id)
