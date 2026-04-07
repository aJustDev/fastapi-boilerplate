from dataclasses import dataclass

from app.core.events.bus import EventBus
from app.core.exceptions import NotFoundError
from app.repos.items.item import ItemRepo


@dataclass(slots=True)
class DeleteItemUseCase:
    item_repo: ItemRepo
    event_bus: EventBus

    async def execute(self, item_id: int) -> None:
        item = await self.item_repo.get_by_id(item_id)
        if not item:
            raise NotFoundError("Item", item_id)

        await self.item_repo.delete(item)

        await self.event_bus.publish(
            event_type="item.deleted",
            payload={"item_id": item_id},
        )
