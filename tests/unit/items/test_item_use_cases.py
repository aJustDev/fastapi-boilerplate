from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.models.items.item import ItemORM
from app.use_cases.items.create_item import CreateItemUseCase
from app.use_cases.items.delete_item import DeleteItemUseCase
from app.use_cases.items.get_item import GetItemUseCase
from app.use_cases.items.list_items import ListItemsCursorUseCase, ListItemsUseCase
from app.use_cases.items.update_item import UpdateItemUseCase


class TestCreateItemUseCase:
    async def test_create_builds_orm_and_publishes_event(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        created_item = MagicMock(spec=ItemORM)
        created_item.id = 1
        created_item.name = "Test Item"
        mock_repo.create.return_value = created_item
        uc = CreateItemUseCase(mock_repo, mock_event_bus)

        result = await uc.execute(
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
        mock_event_bus.publish.assert_awaited_once()

    async def test_create_uses_defaults(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        mock_repo.create.return_value = MagicMock(spec=ItemORM, id=1, name="Item")
        uc = CreateItemUseCase(mock_repo, mock_event_bus)

        await uc.execute(name="Item", owner_id=1)

        call_arg = mock_repo.create.call_args[0][0]
        assert call_arg.category == "general"
        assert call_arg.priority == 0


class TestGetItemUseCase:
    async def test_get_found(self):
        mock_repo = AsyncMock()
        item = MagicMock(spec=ItemORM)
        mock_repo.get_by_id.return_value = item
        uc = GetItemUseCase(mock_repo)

        result = await uc.execute(1)

        assert result is item
        mock_repo.get_by_id.assert_awaited_once_with(1)

    async def test_get_not_found(self):
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None
        uc = GetItemUseCase(mock_repo)

        with pytest.raises(NotFoundError, match="Item not found"):
            await uc.execute(999)


class TestUpdateItemUseCase:
    async def test_update_and_publishes_event(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        existing_item = MagicMock(spec=ItemORM)
        updated_item = MagicMock(spec=ItemORM, id=1, name="Updated")
        mock_repo.get_by_id.return_value = existing_item
        mock_repo.update.return_value = updated_item
        uc = UpdateItemUseCase(mock_repo, mock_event_bus)

        result = await uc.execute(1, {"name": "Updated"})

        assert result is updated_item
        mock_repo.get_by_id.assert_awaited_once_with(1)
        mock_repo.update.assert_awaited_once_with(existing_item, {"name": "Updated"})
        mock_event_bus.publish.assert_awaited_once()


class TestDeleteItemUseCase:
    async def test_delete_and_publishes_event(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        existing_item = MagicMock(spec=ItemORM)
        mock_repo.get_by_id.return_value = existing_item
        uc = DeleteItemUseCase(mock_repo, mock_event_bus)

        await uc.execute(1)

        mock_repo.get_by_id.assert_awaited_once_with(1)
        mock_repo.delete.assert_awaited_once_with(existing_item)
        mock_event_bus.publish.assert_awaited_once()

    async def test_delete_not_found(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        mock_repo.get_by_id.return_value = None
        uc = DeleteItemUseCase(mock_repo, mock_event_bus)

        with pytest.raises(NotFoundError):
            await uc.execute(999)


class TestListItemsUseCase:
    async def test_list_paginated_delegates(self):
        mock_repo = AsyncMock()
        items = [MagicMock(spec=ItemORM)]
        mock_repo.list_paginated.return_value = (items, 1)
        uc = ListItemsUseCase(mock_repo)

        result = await uc.execute(
            page=2, page_size=10, order_by="name", order_dir="desc", filters={"category": "tools"}
        )

        assert result == (items, 1)
        mock_repo.list_paginated.assert_awaited_once_with(
            page=2, page_size=10, order_by="name", order_dir="desc", filters={"category": "tools"}
        )


class TestListItemsCursorUseCase:
    async def test_list_cursor_delegates(self):
        mock_repo = AsyncMock()
        items = [MagicMock(spec=ItemORM)]
        mock_repo.list_cursor.return_value = (items, "next_cursor", True)
        uc = ListItemsCursorUseCase(mock_repo)

        result = await uc.execute(
            cursor="abc", limit=10, order_by="id", order_dir="asc", filters=None
        )

        assert result == (items, "next_cursor", True)
        mock_repo.list_cursor.assert_awaited_once_with(
            cursor="abc", limit=10, order_by="id", order_dir="asc", filters=None
        )
