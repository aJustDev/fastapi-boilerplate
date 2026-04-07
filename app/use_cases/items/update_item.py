from dataclasses import dataclass
from typing import Any

from app.core.events.bus import EventBus
from app.core.exceptions import NotFoundError
from app.models.items.item import ItemORM
from app.repos.items.item import ItemRepo


@dataclass(slots=True)
class UpdateItemUseCase:
    item_repo: ItemRepo
    event_bus: EventBus

    async def execute(self, item_id: int, data: dict[str, Any]) -> ItemORM:
        item = await self.item_repo.get_by_id(item_id)
        if not item:
            raise NotFoundError("Item", item_id)

        item = await self.item_repo.update(item, data)

        await self.event_bus.publish(
            event_type="item.updated",
            payload={
                "item_id": item.id,
                "name": item.name,
                "changes": list(data.keys()),
            },
        )

        return item
