from sqlalchemy import Select, select

from app.core.repo import BaseRepo, FieldMapping
from app.items.models.item import ItemORM


class ItemRepo(BaseRepo[ItemORM]):
    model = ItemORM
    map_field: dict[str, FieldMapping] = {
        "name": {"column": ItemORM.name, "op": "ilike"},
        "category": {"column": ItemORM.category, "op": "eq"},
        "priority": {"column": ItemORM.priority, "op": "eq"},
        "is_active": {"column": ItemORM.is_active, "op": "eq"},
        "owner_id": {"column": ItemORM.owner_id, "op": "eq"},
    }

    def _base_select(self) -> Select:
        return select(ItemORM)

    # `owner_id=None` means every owner (see app/items/services/access.py).

    async def get_distinct_categories(self, owner_id: int | None = None) -> list[str]:
        stmt = select(ItemORM.category).distinct().order_by(ItemORM.category)
        if owner_id is not None:
            stmt = stmt.where(ItemORM.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_distinct_priorities(self, owner_id: int | None = None) -> list[int]:
        stmt = select(ItemORM.priority).distinct().order_by(ItemORM.priority)
        if owner_id is not None:
            stmt = stmt.where(ItemORM.owner_id == owner_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
