from dataclasses import dataclass
from typing import Any

from app.core.events.bus import EventBus
from app.items.models.item import ItemORM
from app.items.repos.item import ItemRepo
from app.items.services.access import Actor, ensure_access


@dataclass(slots=True)
class UpdateItemUseCase:
    item_repo: ItemRepo
    event_bus: EventBus

    async def execute(self, item_id: int, data: dict[str, Any], actor: Actor) -> ItemORM:
        item = ensure_access(await self.item_repo.get_by_id(item_id), item_id, actor)

        item = await self.item_repo.update(item, data)

        await self.event_bus.publish(
            event_type="item.updated",
            aggregate_id=item.id,
            payload={
                "item_id": item.id,
                "name": item.name,
                "changes": list(data.keys()),
            },
        )

        return item
