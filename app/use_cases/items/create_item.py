from dataclasses import dataclass

from app.core.events.bus import EventBus
from app.models.items.item import ItemORM
from app.repos.items.item import ItemRepo


@dataclass(slots=True)
class CreateItemUseCase:
    item_repo: ItemRepo
    event_bus: EventBus

    async def execute(
        self,
        name: str,
        owner_id: int,
        description: str | None = None,
        category: str = "general",
        priority: int = 0,
    ) -> ItemORM:
        item = ItemORM(
            name=name,
            description=description,
            category=category,
            priority=priority,
            owner_id=owner_id,
        )
        item = await self.item_repo.create(item)

        await self.event_bus.publish(
            event_type="item.created",
            payload={
                "item_id": item.id,
                "name": item.name,
                "owner_id": owner_id,
            },
        )

        return item
