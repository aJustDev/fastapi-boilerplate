"""Integration tests for BaseRepo edge cases -- cursor pagination, window functions, filters.

Uses SampleRepo (tests/integration/core/sample.py), a repository of the tests' own,
against real PostgreSQL.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models.user import UserORM
from app.core.exceptions import InvalidCursorError
from app.core.repo import decode_cursor
from tests.integration.core.sample import SampleORM, SampleRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def repo(db_session: AsyncSession, sample_table: None) -> SampleRepo:
    return SampleRepo(db_session)


async def _seed(repo: SampleRepo, seed_user: UserORM, items_data: list[tuple]) -> list[SampleORM]:
    """Seed items from (name, category, priority) tuples."""
    items = []
    for name, category, priority in items_data:
        item = await repo.create(
            SampleORM(name=name, category=category, priority=priority, owner_id=seed_user.id)
        )
        items.append(item)
    return items


# -- Cursor composite sort with tiebreaker --------------------------------


class TestCursorCompositSort:
    async def test_asc_sort_with_duplicate_values(self, repo: SampleRepo, seed_user: UserORM):
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

    async def test_desc_sort_with_tiebreaker(self, repo: SampleRepo, seed_user: UserORM):
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

    async def test_cursor_encodes_sort_field_and_id(self, repo: SampleRepo, seed_user: UserORM):
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
    async def test_cursor_by_name_asc(self, repo: SampleRepo, seed_user: UserORM):
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

    async def test_cursor_by_name_desc(self, repo: SampleRepo, seed_user: UserORM):
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
    async def test_total_count_consistent_across_pages(self, repo: SampleRepo, seed_user: UserORM):
        """COUNT(*) OVER() should return the unfiltered total, not per-page."""
        await _seed(repo, seed_user, [(f"Item {i}", "general", 0) for i in range(12)])

        _, total_p1 = await repo.list_paginated(page=1, page_size=5)
        _, total_p2 = await repo.list_paginated(page=2, page_size=5)
        _, total_p3 = await repo.list_paginated(page=3, page_size=5)

        assert total_p1 == total_p2 == total_p3 == 12

    async def test_total_count_respects_filters(self, repo: SampleRepo, seed_user: UserORM):
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
    async def test_filter_by_owner_id(self, repo: SampleRepo, seed_user: UserORM):
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

    async def test_filter_unknown_field_ignored(self, repo: SampleRepo, seed_user: UserORM):
        await _seed(repo, seed_user, [("Item", "general", 0)])

        items, total = await repo.list_paginated(filters={"nonexistent_field": "value"})

        # Unknown filter is ignored, returns all items
        assert total == 1

    async def test_filter_none_value_skipped(self, repo: SampleRepo, seed_user: UserORM):
        await _seed(repo, seed_user, [("Item", "general", 0)])

        items, total = await repo.list_paginated(filters={"category": None})

        assert total == 1


# -- Edge cases -----------------------------------------------------------


class TestEdgeCases:
    async def test_empty_table_offset(self, repo: SampleRepo):
        items, total = await repo.list_paginated(page=1, page_size=20)

        assert items == []
        assert total == 0

    async def test_empty_table_cursor(self, repo: SampleRepo):
        items, next_cursor, has_more = await repo.list_cursor(limit=20)

        assert items == []
        assert next_cursor is None
        assert has_more is False

    async def test_single_item_cursor(self, repo: SampleRepo, seed_user: UserORM):
        await _seed(repo, seed_user, [("Only", "general", 0)])

        items, next_cursor, has_more = await repo.list_cursor(limit=10)

        assert len(items) == 1
        assert next_cursor is None
        assert has_more is False


# -- CRUD -----------------------------------------------------------------


class TestCrud:
    async def test_create_returns_the_stored_row(self, repo: SampleRepo):
        created = await repo.create(SampleORM(name="new", owner_id=1))

        assert created.id >= 1
        assert created.created_at is not None  # set by the database, read back
        assert created.updated_at is None
        assert (await repo.get_by_id(created.id)) is created

    async def test_update_changes_the_fields_given_and_stamps_the_row(self, repo: SampleRepo):
        created = await repo.create(SampleORM(name="before", category="books", owner_id=1))

        updated = await repo.update(created, {"name": "after", "no_such_field": 1})

        assert (updated.name, updated.category) == ("after", "books")
        assert updated.updated_at is not None

    async def test_delete_removes_the_row(self, repo: SampleRepo):
        created = await repo.create(SampleORM(name="gone", owner_id=1))

        await repo.delete(created)

        assert await repo.get_by_id(created.id) is None

    async def test_get_by_id_of_nothing_is_none(self, repo: SampleRepo):
        assert await repo.get_by_id(999_999) is None


# -- Every sort field, every direction ------------------------------------

# Few distinct values over many rows: almost every row ties with others on the sort
# field, which is when an ORDER BY without a tiebreaker starts shuffling pages.
SORT_FIELDS = ["id", "name", "category", "priority", "created_at"]


async def _seed_with_ties(repo: SampleRepo, count: int) -> list[int]:
    rows = [
        await repo.create(
            SampleORM(
                name=f"row {n % 3}", category=("books", "sports")[n % 2], priority=n % 2, owner_id=1
            )
        )
        for n in range(count)
    ]
    return [row.id for row in rows]


@pytest.mark.parametrize("order_dir", ["asc", "desc"])
@pytest.mark.parametrize("order_by", SORT_FIELDS)
async def test_offset_pages_cover_every_row_once_in_order(
    repo: SampleRepo, order_by: str, order_dir: str
):
    created = await _seed_with_ties(repo, 40)

    seen = []
    for page in range(1, 7):
        rows, total = await repo.list_paginated(
            page=page, page_size=7, order_by=order_by, order_dir=order_dir
        )
        assert total == len(created)
        seen.extend(rows)

    assert sorted(row.id for row in seen) == sorted(created)
    keys = [(getattr(row, order_by), row.id) for row in seen]
    assert keys == sorted(keys, reverse=order_dir == "desc")


@pytest.mark.parametrize("order_dir", ["asc", "desc"])
@pytest.mark.parametrize("order_by", SORT_FIELDS)
async def test_cursor_pages_cover_every_row_once_in_order(
    repo: SampleRepo, order_by: str, order_dir: str
):
    created = await _seed_with_ties(repo, 20)

    seen, cursor = [], None
    for _ in range(len(created) + 1):  # a broken cursor must not loop forever
        rows, cursor, has_more = await repo.list_cursor(
            cursor=cursor, limit=3, order_by=order_by, order_dir=order_dir
        )
        seen.extend(rows)
        if not has_more:
            break

    assert sorted(row.id for row in seen) == sorted(created)
    keys = [(getattr(row, order_by), row.id) for row in seen]
    assert keys == sorted(keys, reverse=order_dir == "desc")


async def test_a_cursor_issued_for_another_order_is_rejected(repo: SampleRepo):
    await _seed_with_ties(repo, 5)
    _, by_name, _ = await repo.list_cursor(limit=2, order_by="name")

    with pytest.raises(InvalidCursorError):
        await repo.list_cursor(limit=2, order_by="priority", cursor=by_name)


async def test_a_page_past_the_end_still_reports_the_total(repo: SampleRepo):
    await _seed_with_ties(repo, 5)

    rows, total = await repo.list_paginated(page=99, page_size=10)

    assert (rows, total) == ([], 5)


# -- Filters --------------------------------------------------------------


class TestFilters:
    async def test_range_operators(self, repo: SampleRepo):
        for priority in (1, 2, 3):
            await repo.create(SampleORM(name="x", priority=priority, owner_id=1))

        at_least_2, _ = await repo.list_paginated(filters={"min_priority": 2})
        at_most_2, _ = await repo.list_paginated(filters={"max_priority": 2})

        assert sorted(row.priority for row in at_least_2) == [2, 3]
        assert sorted(row.priority for row in at_most_2) == [1, 2]

    async def test_the_text_filter_matches_its_characters_literally(self, repo: SampleRepo):
        # % and _ are wildcards of LIKE. Sent by a client they are just characters.
        for name in ("alpha", "bravo", "100%_done"):
            await repo.create(SampleORM(name=name, owner_id=1))

        async def names(pattern: str) -> list[str]:
            rows, _ = await repo.list_paginated(filters={"name": pattern})
            return [row.name for row in rows]

        assert await names("%") == ["100%_done"]
        assert await names("_") == ["100%_done"]
        assert await names("0%_d") == ["100%_done"]
        assert await names("ALPH") == ["alpha"]  # still a case-insensitive "contains"


# -- Scope ----------------------------------------------------------------


class TestScope:
    """`scope` is what the caller may see; `filters` only narrow inside it."""

    async def _seed(self, repo: SampleRepo) -> None:
        for owner_id, category in [(1, "books"), (1, "sports"), (2, "books"), (2, "sports")]:
            await repo.create(SampleORM(name="x", category=category, owner_id=owner_id))

    async def test_offset_lists_and_counts_only_the_scope(self, repo: SampleRepo):
        await self._seed(repo)

        rows, total = await repo.list_paginated(scope=SampleORM.owner_id == 1)

        assert total == 2
        assert {row.owner_id for row in rows} == {1}

    async def test_cursor_lists_only_the_scope(self, repo: SampleRepo):
        await self._seed(repo)

        first, cursor, has_more = await repo.list_cursor(limit=1, scope=SampleORM.owner_id == 1)
        second, _, more = await repo.list_cursor(
            limit=5, cursor=cursor, scope=SampleORM.owner_id == 1
        )

        assert has_more and not more
        assert [row.owner_id for row in first + second] == [1, 1]

    async def test_a_filter_cannot_widen_the_scope(self, repo: SampleRepo):
        await self._seed(repo)

        rows, total = await repo.list_paginated(
            filters={"owner_id": 2, "category": "books"}, scope=SampleORM.owner_id == 1
        )

        assert (rows, total) == ([], 0)

    async def test_the_total_past_the_last_page_respects_the_scope(self, repo: SampleRepo):
        await self._seed(repo)

        rows, total = await repo.list_paginated(page=9, scope=SampleORM.owner_id == 1)

        assert (rows, total) == ([], 2)
