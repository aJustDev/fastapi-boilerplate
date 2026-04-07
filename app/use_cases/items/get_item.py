from dataclasses import dataclass

from app.core.exceptions import NotFoundError
from app.models.items.item import ItemORM
from app.repos.items.item import ItemRepo


@dataclass(slots=True)
class GetItemUseCase:
    item_repo: ItemRepo

    async def execute(self, item_id: int) -> ItemORM:
        item = await self.item_repo.get_by_id(item_id)
        if not item:
            raise NotFoundError("Item", item_id)
        return item
