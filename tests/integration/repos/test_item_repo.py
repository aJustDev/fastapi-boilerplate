import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth.user import UserORM
from app.models.items.item import ItemORM
from app.repos.items.item import ItemRepo

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


@pytest.fixture
def repo(db_session: AsyncSession) -> ItemRepo:
    return ItemRepo(db_session)


# -- CRUD -----------------------------------------------------------------


class TestCreate:
    async def test_create_item(self, repo: ItemRepo, seed_user: UserORM):
        item = ItemORM(
            name="New Item",
            description="A test item",
            category="electronics",
            priority=1,
            owner_id=seed_user.id,
        )
        created = await repo.create(item)

        assert created.id is not None
        assert created.name == "New Item"
        assert created.category == "electronics"
        assert created.owner_id == seed_user.id
        assert created.created_at is not None

    async def test_create_item_fk_violation(self, repo: ItemRepo):
        item = ItemORM(
            name="Orphan",
            category="general",
            priority=0,
            owner_id=999999,
        )
        with pytest.raises(IntegrityError):
            await repo.create(item)


class TestGetById:
    async def test_get_existing(self, repo: ItemRepo, seed_user: UserORM):
        item = ItemORM(name="Findable", category="general", priority=0, owner_id=seed_user.id)
        created = await repo.create(item)

        found = await repo.get_by_id(created.id)

        assert found is not None
        assert found.id == created.id
        assert found.name == "Findable"

    async def test_get_nonexistent(self, repo: ItemRepo):
        found = await repo.get_by_id(999999)
        assert found is None


class TestUpdate:
    async def test_update_fields(self, repo: ItemRepo, seed_user: UserORM):
        item = ItemORM(name="Original", category="general", priority=0, owner_id=seed_user.id)
        created = await repo.create(item)

        updated = await repo.update(created, {"name": "Updated", "priority": 5})

        assert updated.name == "Updated"
        assert updated.priority == 5
        assert updated.id == created.id


class TestDelete:
    async def test_delete_item(self, repo: ItemRepo, seed_user: UserORM):
        item = ItemORM(name="Deletable", category="general", priority=0, owner_id=seed_user.id)
        created = await repo.create(item)

        await repo.delete(created)

        found = await repo.get_by_id(created.id)
        assert found is None


# -- Offset pagination ----------------------------------------------------


class TestOffsetPagination:
    async def _seed_items(self, repo: ItemRepo, seed_user: UserORM, count: int) -> list[ItemORM]:
        items = []
        for i in range(count):
            item = ItemORM(
                name=f"Item {i:03d}",
                category="electronics" if i % 2 == 0 else "books",
                priority=i % 4,
                owner_id=seed_user.id,
            )
            created = await repo.create(item)
            items.append(created)
        return items

    async def test_first_page(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_items(repo, seed_user, 10)

        items, total = await repo.list_paginated(page=1, page_size=5)

        assert len(items) == 5
        assert total == 10

    async def test_second_page(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_items(repo, seed_user, 10)

        items, total = await repo.list_paginated(page=2, page_size=5)

        assert len(items) == 5
        assert total == 10

    async def test_last_page_partial(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_items(repo, seed_user, 7)

        items, total = await repo.list_paginated(page=2, page_size=5)

        assert len(items) == 2
        assert total == 7

    async def test_empty_result(self, repo: ItemRepo):
        items, total = await repo.list_paginated(
            page=1, page_size=20, filters={"category": "nonexistent"}
        )

        assert items == []
        assert total == 0

    async def test_window_count_accuracy(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_items(repo, seed_user, 15)

        page1_items, total1 = await repo.list_paginated(page=1, page_size=5)
        page2_items, total2 = await repo.list_paginated(page=2, page_size=5)
        page3_items, total3 = await repo.list_paginated(page=3, page_size=5)

        assert total1 == total2 == total3 == 15
        assert len(page1_items) == len(page2_items) == len(page3_items) == 5

        all_ids = {i.id for i in page1_items + page2_items + page3_items}
        assert len(all_ids) == 15


# -- Filtering ------------------------------------------------------------


class TestFiltering:
    async def _seed_mixed_items(self, repo: ItemRepo, seed_user: UserORM) -> list[ItemORM]:
        data = [
            ("Laptop Pro", "electronics", 3, True),
            ("Python Book", "books", 1, True),
            ("Screwdriver", "tools", 2, False),
            ("Tablet Mini", "electronics", 2, True),
            ("Cooking Guide", "books", 1, False),
        ]
        items = []
        for name, category, priority, is_active in data:
            item = ItemORM(
                name=name,
                category=category,
                priority=priority,
                is_active=is_active,
                owner_id=seed_user.id,
            )
            created = await repo.create(item)
            items.append(created)
        return items

    async def test_filter_by_category_eq(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_mixed_items(repo, seed_user)

        items, total = await repo.list_paginated(filters={"category": "electronics"})

        assert total == 2
        assert all(i.category == "electronics" for i in items)

    async def test_filter_by_name_ilike(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_mixed_items(repo, seed_user)

        items, total = await repo.list_paginated(filters={"name": "book"})

        assert total == 1
        assert "Book" in items[0].name

    async def test_filter_by_is_active(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_mixed_items(repo, seed_user)

        items, total = await repo.list_paginated(filters={"is_active": False})

        assert total == 2
        assert all(not i.is_active for i in items)

    async def test_combined_filters(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_mixed_items(repo, seed_user)

        items, total = await repo.list_paginated(filters={"category": "books", "is_active": True})

        assert total == 1
        assert items[0].name == "Python Book"


# -- Ordering -------------------------------------------------------------


class TestOrdering:
    async def _seed_ordered_items(self, repo: ItemRepo, seed_user: UserORM):
        for name, priority in [("C", 2), ("A", 1), ("B", 3)]:
            await repo.create(
                ItemORM(name=name, category="general", priority=priority, owner_id=seed_user.id)
            )

    async def test_order_by_name_asc(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_ordered_items(repo, seed_user)

        items, _ = await repo.list_paginated(order_by="name", order_dir="asc")

        names = [i.name for i in items]
        assert names == ["A", "B", "C"]

    async def test_order_by_priority_desc(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_ordered_items(repo, seed_user)

        items, _ = await repo.list_paginated(order_by="priority", order_dir="desc")

        priorities = [i.priority for i in items]
        assert priorities == [3, 2, 1]

    async def test_unknown_order_field_falls_back_to_id(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_ordered_items(repo, seed_user)

        items, _ = await repo.list_paginated(order_by="nonexistent_field", order_dir="asc")

        ids = [i.id for i in items]
        assert ids == sorted(ids)


# -- Cursor pagination ----------------------------------------------------


class TestCursorPagination:
    async def _seed_cursor_items(self, repo: ItemRepo, seed_user: UserORM, count: int = 7):
        items = []
        for i in range(count):
            item = await repo.create(
                ItemORM(
                    name=f"Cursor Item {i:03d}",
                    category="general",
                    priority=i % 3,
                    owner_id=seed_user.id,
                )
            )
            items.append(item)
        return items

    async def test_first_page_no_cursor(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_cursor_items(repo, seed_user, 7)

        items, next_cursor, has_more = await repo.list_cursor(limit=3)

        assert len(items) == 3
        assert has_more is True
        assert next_cursor is not None

    async def test_full_traversal(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_cursor_items(repo, seed_user, 7)
        all_items = []
        cursor = None

        for _ in range(10):  # safety limit
            items, cursor, has_more = await repo.list_cursor(cursor=cursor, limit=3)
            all_items.extend(items)
            if not has_more:
                break

        assert len(all_items) == 7
        ids = [i.id for i in all_items]
        assert ids == sorted(ids)
        assert len(set(ids)) == 7

    async def test_cursor_with_sort_field(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_cursor_items(repo, seed_user, 5)
        all_items = []
        cursor = None

        for _ in range(10):
            items, cursor, has_more = await repo.list_cursor(
                cursor=cursor, limit=2, order_by="name", order_dir="asc"
            )
            all_items.extend(items)
            if not has_more:
                break

        assert len(all_items) == 5
        names = [i.name for i in all_items]
        assert names == sorted(names)

    async def test_cursor_desc_order(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_cursor_items(repo, seed_user, 5)
        all_items = []
        cursor = None

        for _ in range(10):
            items, cursor, has_more = await repo.list_cursor(
                cursor=cursor, limit=2, order_by="id", order_dir="desc"
            )
            all_items.extend(items)
            if not has_more:
                break

        assert len(all_items) == 5
        ids = [i.id for i in all_items]
        assert ids == sorted(ids, reverse=True)

    async def test_cursor_exact_limit_boundary(self, repo: ItemRepo, seed_user: UserORM):
        await self._seed_cursor_items(repo, seed_user, 3)

        items, next_cursor, has_more = await repo.list_cursor(limit=3)

        assert len(items) == 3
        assert has_more is False
        assert next_cursor is None

    async def test_cursor_with_filters(self, repo: ItemRepo, seed_user: UserORM):
        for name, cat in [
            ("A", "electronics"),
            ("B", "books"),
            ("C", "electronics"),
            ("D", "books"),
        ]:
            await repo.create(ItemORM(name=name, category=cat, priority=0, owner_id=seed_user.id))

        items, _, has_more = await repo.list_cursor(limit=10, filters={"category": "electronics"})

        assert len(items) == 2
        assert all(i.category == "electronics" for i in items)
        assert has_more is False


# -- Distinct queries -----------------------------------------------------


class TestDistinctQueries:
    async def test_get_distinct_categories(self, repo: ItemRepo, seed_user: UserORM):
        for cat in ["electronics", "books", "electronics", "tools"]:
            await repo.create(
                ItemORM(name=f"Item {cat}", category=cat, priority=0, owner_id=seed_user.id)
            )

        categories = await repo.get_distinct_categories()

        assert categories == ["books", "electronics", "tools"]

    async def test_get_distinct_priorities(self, repo: ItemRepo, seed_user: UserORM):
        for p in [3, 1, 2, 1, 3]:
            await repo.create(
                ItemORM(name=f"Item p{p}", category="general", priority=p, owner_id=seed_user.id)
            )

        priorities = await repo.get_distinct_priorities()

        assert priorities == [1, 2, 3]
