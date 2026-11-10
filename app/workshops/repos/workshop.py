from typing import Any, NewType

from sqlalchemy import func, or_, select, update

from app.core.db import rowcount
from app.core.repo import BaseRepo, FieldMapping
from app.workshops.models.workshop import WorkshopORM
from app.workshops.schemas.workshop import WorkshopStatus

LockedWorkshop = NewType("LockedWorkshop", WorkshopORM)
"""A workshop whose row this transaction holds locked: what `get_for_update` returns.

The rules about seats take this type and not WorkshopORM, so handing them a workshop
read without the lock is an error for mypy instead of a race in production."""


class WorkshopRepo(BaseRepo[WorkshopORM]):
    model = WorkshopORM
    map_field: dict[str, FieldMapping] = {
        "status": {"column": WorkshopORM.status, "op": "eq"},
        "title": {"column": WorkshopORM.title, "op": "ilike"},
        "starts_after": {"column": WorkshopORM.starts_at, "op": "gte"},
    }

    async def get_for_update(self, workshop_id: int) -> LockedWorkshop | None:
        """The workshop with its row locked until the transaction ends.

        Whoever changes the seats or the enrollments of a workshop takes this lock first,
        so those changes happen one after another (app/workshops/services/seating.py).
        `populate_existing` because a copy read earlier in the session would be stale.
        """
        stmt = (
            select(WorkshopORM)
            .where(WorkshopORM.id == workshop_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        workshop = (await self.session.execute(stmt)).scalars().first()
        return None if workshop is None else LockedWorkshop(workshop)

    async def list_visible(
        self,
        viewer_id: int | None,
        *,
        cursor: str | None = None,
        limit: int = 20,
        order_by: str | None = None,
        order_dir: str = "asc",
        filters: dict[str, Any] | None = None,
    ) -> tuple[list[WorkshopORM], str | None, bool]:
        """A page of what `viewer_id` may see: every workshop that left draft, and its own
        drafts. `None` means no restriction (see app/workshops/services/access.py)."""
        scope = (
            None
            if viewer_id is None
            else or_(
                WorkshopORM.status != WorkshopStatus.DRAFT,
                WorkshopORM.organizer_id == viewer_id,
            )
        )
        return await self.list_cursor(
            cursor=cursor,
            limit=limit,
            order_by=order_by,
            order_dir=order_dir,
            filters=filters,
            scope=scope,
        )

    async def finish_ended(self) -> int:
        """Published workshops whose end has passed become finished; returns how many."""
        result = await self.session.execute(
            update(WorkshopORM)
            .where(
                WorkshopORM.status == WorkshopStatus.PUBLISHED,
                WorkshopORM.ends_at <= func.now(),
            )
            .values(status=WorkshopStatus.FINISHED)
        )
        return rowcount(result)
