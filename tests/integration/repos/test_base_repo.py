"""Integration tests for BaseRepo edge cases -- cursor pagination, window functions, filters.

Uses ItemRepo as a concrete implementation of BaseRepo[T] against real PostgreSQL.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.user import UserORM
from app.models.items.item import ItemORM
from app.repos.base import decode_cursor
from app.repos.items.item import ItemRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def repo(db_session: AsyncSession) -> ItemRepo:
    return ItemRepo(db_session)


async def _seed(repo: ItemRepo, seed_user: UserORM, items_data: list[tuple]) -> list[ItemORM]:
    """Seed items from (name, category, priority) tuples."""
    items = []
    for name, category, priority in items_data:
        item = await repo.create(
            ItemORM(name=name, category=category, priority=priority, owner_id=seed_user.id)
        )
        items.append(item)
    return items


# -- Cursor composite sort with tiebreaker --------------------------------


class TestCursorCompositSort:
    async def test_asc_sort_with_duplicate_values(self, repo: ItemRepo, seed_user: UserORM):
        """Items with same priority should be ordered by id tiebreaker."""
        await _seed(
            repo,
            seed_user,
            [
                ("A", "general", 1),
                ("B", "general", 1),
                ("C", "general", 1),
                ("D", "general", 2),
                ("E", "general", 2),
            ],
        )

        all_items = []
        cursor = None
        for _ in range(10):
            items, cursor, has_more = await repo.list_cursor(
                cursor=cursor, limit=2, order_by="priority", order_dir="asc"
            )
            all_items.extend(items)
            if not has_more:
                break

        assert len(all_items) == 5
        # Priority should be non-decreasing
        priorities = [i.priority for i in all_items]
        assert priorities == sorted(priorities)
        # Within same priority, ids should be ascending (tiebreaker)
        p1_ids = [i.id for i in all_items if i.priority == 1]
        assert p1_ids == sorted(p1_ids)

    async def test_desc_sort_with_tiebreaker(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(
            repo,
            seed_user,
            [
                ("A", "general", 1),
                ("B", "general", 2),
                ("C", "general", 2),
                ("D", "general", 3),
            ],
        )

        all_items = []
        cursor = None
        for _ in range(10):
            items, cursor, has_more = await repo.list_cursor(
                cursor=cursor, limit=2, order_by="priority", order_dir="desc"
            )
            all_items.extend(items)
            if not has_more:
                break

        assert len(all_items) == 4
        priorities = [i.priority for i in all_items]
        assert priorities == sorted(priorities, reverse=True)

    async def test_cursor_encodes_sort_field_and_id(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(
            repo,
            seed_user,
            [
                ("A", "general", 1),
                ("B", "general", 2),
                ("C", "general", 3),
            ],
        )

        items, next_cursor, has_more = await repo.list_cursor(
            limit=2, order_by="priority", order_dir="asc"
        )

        assert next_cursor is not None
        cursor_data = decode_cursor(next_cursor)
        assert "id" in cursor_data
        assert "priority" in cursor_data
        assert cursor_data["id"] == items[-1].id
        assert cursor_data["priority"] == items[-1].priority


# -- Cursor with string sort field ----------------------------------------


class TestCursorStringSort:
    async def test_cursor_by_name_asc(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(
            repo,
            seed_user,
            [
                ("Charlie", "general", 0),
                ("Alpha", "general", 0),
                ("Bravo", "general", 0),
                ("Delta", "general", 0),
            ],
        )

        all_items = []
        cursor = None
        for _ in range(10):
            items, cursor, has_more = await repo.list_cursor(
                cursor=cursor, limit=2, order_by="name", order_dir="asc"
            )
            all_items.extend(items)
            if not has_more:
                break

        names = [i.name for i in all_items]
        assert names == ["Alpha", "Bravo", "Charlie", "Delta"]

    async def test_cursor_by_name_desc(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(
            repo,
            seed_user,
            [
                ("Charlie", "general", 0),
                ("Alpha", "general", 0),
                ("Bravo", "general", 0),
            ],
        )

        all_items = []
        cursor = None
        for _ in range(10):
            items, cursor, has_more = await repo.list_cursor(
                cursor=cursor, limit=1, order_by="name", order_dir="desc"
            )
            all_items.extend(items)
            if not has_more:
                break

        names = [i.name for i in all_items]
        assert names == ["Charlie", "Bravo", "Alpha"]


# -- Window function COUNT(*) OVER() -------------------------------------


class TestWindowCount:
    async def test_total_count_consistent_across_pages(self, repo: ItemRepo, seed_user: UserORM):
        """COUNT(*) OVER() should return the unfiltered total, not per-page."""
        await _seed(repo, seed_user, [(f"Item {i}", "general", 0) for i in range(12)])

        _, total_p1 = await repo.list_paginated(page=1, page_size=5)
        _, total_p2 = await repo.list_paginated(page=2, page_size=5)
        _, total_p3 = await repo.list_paginated(page=3, page_size=5)

        assert total_p1 == total_p2 == total_p3 == 12

    async def test_total_count_respects_filters(self, repo: ItemRepo, seed_user: UserORM):
        """COUNT(*) OVER() should count only filtered rows."""
        await _seed(
            repo,
            seed_user,
            [
                ("E1", "electronics", 0),
                ("E2", "electronics", 0),
                ("B1", "books", 0),
            ],
        )

        items, total = await repo.list_paginated(
            page=1, page_size=10, filters={"category": "electronics"}
        )

        assert total == 2
        assert len(items) == 2


# -- Filter operators (gte, lte via direct model attribute) ---------------


class TestFilterOperators:
    async def test_filter_by_owner_id(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(
            repo,
            seed_user,
            [
                ("Owned", "general", 0),
            ],
        )

        items, total = await repo.list_paginated(filters={"owner_id": seed_user.id})

        assert total == 1
        assert items[0].owner_id == seed_user.id

    async def test_filter_unknown_field_ignored(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(repo, seed_user, [("Item", "general", 0)])

        items, total = await repo.list_paginated(filters={"nonexistent_field": "value"})

        # Unknown filter is ignored, returns all items
        assert total == 1

    async def test_filter_none_value_skipped(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(repo, seed_user, [("Item", "general", 0)])

        items, total = await repo.list_paginated(filters={"category": None})

        assert total == 1


# -- Edge cases -----------------------------------------------------------


class TestEdgeCases:
    async def test_empty_table_offset(self, repo: ItemRepo):
        items, total = await repo.list_paginated(page=1, page_size=20)

        assert items == []
        assert total == 0

    async def test_empty_table_cursor(self, repo: ItemRepo):
        items, next_cursor, has_more = await repo.list_cursor(limit=20)

        assert items == []
        assert next_cursor is None
        assert has_more is False

    async def test_single_item_cursor(self, repo: ItemRepo, seed_user: UserORM):
        await _seed(repo, seed_user, [("Only", "general", 0)])

        items, next_cursor, has_more = await repo.list_cursor(limit=10)

        assert len(items) == 1
        assert next_cursor is None
        assert has_more is False
