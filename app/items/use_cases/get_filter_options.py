from dataclasses import dataclass

from app.items.repos.item import ItemRepo
from app.items.schemas.item import ItemFilterOptions
from app.items.services.access import Actor, owner_filter


@dataclass(slots=True)
class GetFilterOptionsUseCase:
    item_repo: ItemRepo

    async def execute(self, actor: Actor) -> ItemFilterOptions:
        """The values worth offering as filters: the ones present in the items the actor sees."""
        owner_id = owner_filter(actor)
        return ItemFilterOptions(
            category=await self.item_repo.get_distinct_categories(owner_id),
            priority=await self.item_repo.get_distinct_priorities(owner_id),
            is_active=[True, False],
        )
