from dataclasses import dataclass

from app.core.events.bus import EventBus
from app.items.repos.item import ItemRepo
from app.items.services.access import Actor, ensure_access


@dataclass(slots=True)
class DeleteItemUseCase:
    item_repo: ItemRepo
    event_bus: EventBus

    async def execute(self, item_id: int, actor: Actor) -> None:
        item = ensure_access(await self.item_repo.get_by_id(item_id), item_id, actor)

        await self.item_repo.delete(item)

        await self.event_bus.publish(
            event_type="item.deleted",
            payload={"item_id": item_id},
        )
