from dataclasses import dataclass

from app.core.events.bus import EventBus
from app.services.items import ItemService


@dataclass(slots=True)
class DeleteItemUseCase:
    item_service: ItemService
    event_bus: EventBus

    async def execute(self, item_id: int) -> None:
        await self.item_service.delete(item_id)

        await self.event_bus.publish(
            event_type="item.deleted",
            payload={"item_id": item_id},
        )
