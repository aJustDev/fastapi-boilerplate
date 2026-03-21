from dataclasses import dataclass

from app.core.events.bus import EventBus
from app.models.items.item import ItemORM
from app.services.items import ItemService


@dataclass(slots=True)
class CreateItemUseCase:
    item_service: ItemService
    event_bus: EventBus

    async def execute(
        self,
        name: str,
        owner_id: int,
        description: str | None = None,
        category: str = "general",
        priority: int = 0,
    ) -> ItemORM:
        item = await self.item_service.create(name, owner_id, description, category, priority)

        await self.event_bus.publish(
            event_type="item.created",
            payload={
                "item_id": item.id,
                "name": item.name,
                "owner_id": owner_id,
            },
        )

        return item
