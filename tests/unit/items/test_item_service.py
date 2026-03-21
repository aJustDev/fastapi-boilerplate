from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.models.items.item import ItemORM
from app.services.items import ItemService


class TestItemServiceCreate:
    async def test_create_builds_orm_and_delegates(self):
        mock_repo = AsyncMock()
        created_item = MagicMock(spec=ItemORM)
        mock_repo.create.return_value = created_item
        service = ItemService(mock_repo)

        result = await service.create(
            name="Test Item",
            owner_id=1,
            description="A description",
            category="tools",
            priority=3,
        )

        assert result is created_item
        mock_repo.create.assert_awaited_once()
        call_arg = mock_repo.create.call_args[0][0]
        assert isinstance(call_arg, ItemORM)
        assert call_arg.name == "Test Item"
        assert call_arg.owner_id == 1
        assert call_arg.description == "A description"
        assert call_arg.category == "tools"
        assert call_arg.priority == 3

    async def test_create_uses_defaults(self):
        mock_repo = AsyncMock()
        mock_repo.create.return_value = MagicMock(spec=ItemORM)
        service = ItemService(mock_repo)

        await service.create(name="Item", owner_id=1)

        call_arg = mock_repo.create.call_args[0][0]
        assert call_arg.category == "general"
        assert call_arg.priority == 0


class TestItemServiceGet:
    async def test_get_found(self):
        mock_repo = AsyncMock()
        item = MagicMock(spec=ItemORM)
        mock_repo.get_by_id.return_value = item
        service = ItemService(mock_repo)

        result = await service.get(1)

        assert result is item
        mock_repo.get_by_id.assert_awaited_once_with(1)

    async def test_get_not_found(self):
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        service = ItemService(mock_repo)

        with pytest.raises(NotFoundError, match="Item not found"):
            await service.get(999)


class TestItemServiceUpdate:
    async def test_update_delegates(self):
        mock_repo = AsyncMock()
        existing_item = MagicMock(spec=ItemORM)
        updated_item = MagicMock(spec=ItemORM)
        mock_repo.get_by_id.return_value = existing_item
        mock_repo.update.return_value = updated_item
        service = ItemService(mock_repo)

        result = await service.update(1, {"name": "Updated"})

        assert result is updated_item
        mock_repo.get_by_id.assert_awaited_once_with(1)
        mock_repo.update.assert_awaited_once_with(existing_item, {"name": "Updated"})


class TestItemServiceDelete:
    async def test_delete_delegates(self):
        mock_repo = AsyncMock()
        existing_item = MagicMock(spec=ItemORM)
        mock_repo.get_by_id.return_value = existing_item
        service = ItemService(mock_repo)

        await service.delete(1)

        mock_repo.get_by_id.assert_awaited_once_with(1)
        mock_repo.delete.assert_awaited_once_with(existing_item)

    async def test_delete_not_found(self):
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        service = ItemService(mock_repo)

        with pytest.raises(NotFoundError):
            await service.delete(999)


class TestItemServiceListPaginated:
    async def test_list_paginated_delegates(self):
        mock_repo = AsyncMock()
        items = [MagicMock(spec=ItemORM)]
        mock_repo.list.return_value = (items, 1)
        service = ItemService(mock_repo)

        result = await service.list_paginated(
            page=2, page_size=10, order_by="name", order_dir="desc", filters={"category": "tools"}
        )

        assert result == (items, 1)
        mock_repo.list.assert_awaited_once_with(
            page=2, page_size=10, order_by="name", order_dir="desc", filters={"category": "tools"}
        )


class TestItemServiceListCursor:
    async def test_list_cursor_delegates(self):
        mock_repo = AsyncMock()
        items = [MagicMock(spec=ItemORM)]
        mock_repo.list_cursor.return_value = (items, "next_cursor", True)
        service = ItemService(mock_repo)

        result = await service.list_cursor(
            cursor="abc", limit=10, order_by="id", order_dir="asc", filters=None
        )

        assert result == (items, "next_cursor", True)
        mock_repo.list_cursor.assert_awaited_once_with(
            cursor="abc", limit=10, order_by="id", order_dir="asc", filters=None
        )


class TestItemServiceGetFilterOptions:
    async def test_get_filter_options_returns_correct_shape(self):
        mock_repo = AsyncMock()
        mock_repo.get_distinct_categories.return_value = ["general", "tools"]
        mock_repo.get_distinct_priorities.return_value = [0, 1, 2]
        service = ItemService(mock_repo)

        result = await service.get_filter_options()

        assert result == {
            "category": ["general", "tools"],
            "priority": [0, 1, 2],
            "is_active": [True, False],
        }
        mock_repo.get_distinct_categories.assert_awaited_once()
        mock_repo.get_distinct_priorities.assert_awaited_once()
