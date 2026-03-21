from sqlalchemy import Select, distinct, select
from sqlalchemy.orm import selectinload

from app.models.items.item import ItemORM
from app.repos.base import BaseRepo

_list = list


class ItemRepo(BaseRepo[ItemORM]):
    model = ItemORM
    map_field = {
        "name": {"column": ItemORM.name, "op": "ilike"},
        "category": {"column": ItemORM.category, "op": "eq"},
        "priority": {"column": ItemORM.priority, "op": "eq"},
        "is_active": {"column": ItemORM.is_active, "op": "eq"},
        "owner_id": {"column": ItemORM.owner_id, "op": "eq"},
    }

    def _base_select(self) -> Select:
        return select(ItemORM).options(selectinload(ItemORM.owner))

    async def get_distinct_categories(self) -> _list[str]:
        stmt = select(distinct(ItemORM.category)).order_by(ItemORM.category)
        result = await self.session.execute(stmt)
        return _list(result.scalars().all())

    async def get_distinct_priorities(self) -> _list[int]:
        stmt = select(distinct(ItemORM.priority)).order_by(ItemORM.priority)
        result = await self.session.execute(stmt)
        return _list(result.scalars().all())
