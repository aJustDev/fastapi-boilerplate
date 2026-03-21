from dataclasses import dataclass
from typing import Any

from app.core.events.bus import EventBus
from app.models.items.item import ItemORM
from app.services.items import ItemService


@dataclass(slots=True)
class UpdateItemUseCase:
    item_service: ItemService
    event_bus: EventBus

    async def execute(self, item_id: int, data: dict[str, Any]) -> ItemORM:
        item = await self.item_service.update(item_id, data)

        await self.event_bus.publish(
            event_type="item.updated",
            payload={
                "item_id": item.id,
                "name": item.name,
                "changes": list(data.keys()),
            },
        )

        return item
