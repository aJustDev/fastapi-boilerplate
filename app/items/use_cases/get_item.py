from dataclasses import dataclass

from app.items.models.item import ItemORM
from app.items.repos.item import ItemRepo
from app.items.services.access import Actor, ensure_access


@dataclass(slots=True)
class GetItemUseCase:
    item_repo: ItemRepo

    async def execute(self, item_id: int, actor: Actor) -> ItemORM:
        return ensure_access(await self.item_repo.get_by_id(item_id), item_id, actor)
