from unittest.mock import AsyncMock, MagicMock

from app.models.items.item import ItemORM
from app.use_cases.items.create_item import CreateItemUseCase
from app.use_cases.items.delete_item import DeleteItemUseCase
from app.use_cases.items.get_item import GetItemUseCase
from app.use_cases.items.list_items import ListItemsCursorUseCase, ListItemsUseCase
from app.use_cases.items.update_item import UpdateItemUseCase


class TestCreateItemUseCase:
    async def test_delegates_to_service_and_publishes_event(self):
        mock_service = AsyncMock()
        mock_event_bus = AsyncMock()
        item = MagicMock(spec=ItemORM)
        item.id = 42
        item.name = "Item"
        mock_service.create.return_value = item

        uc = CreateItemUseCase(mock_service, mock_event_bus)
        result = await uc.execute(
            name="Item", owner_id=1, description="desc", category="tools", priority=2
        )

        mock_service.create.assert_called_once_with("Item", 1, "desc", "tools", 2)
        mock_event_bus.publish.assert_called_once_with(
            event_type="item.created",
            payload={"item_id": 42, "name": "Item", "owner_id": 1},
        )
        assert result is item

    async def test_delegates_with_defaults(self):
        mock_service = AsyncMock()
        mock_event_bus = AsyncMock()
        item = MagicMock(spec=ItemORM)
        item.id = 1
        item.name = "Item"
        mock_service.create.return_value = item

        uc = CreateItemUseCase(mock_service, mock_event_bus)
        await uc.execute(name="Item", owner_id=1)

        mock_service.create.assert_called_once_with("Item", 1, None, "general", 0)
        mock_event_bus.publish.assert_called_once()


class TestGetItemUseCase:
    async def test_delegates_to_service(self):
        mock_service = AsyncMock()
        item = MagicMock(spec=ItemORM)
        mock_service.get.return_value = item

        uc = GetItemUseCase(mock_service)
        result = await uc.execute(42)

        mock_service.get.assert_called_once_with(42)
        assert result is item


class TestDeleteItemUseCase:
    async def test_delegates_to_service_and_publishes_event(self):
        mock_service = AsyncMock()
        mock_event_bus = AsyncMock()

        uc = DeleteItemUseCase(mock_service, mock_event_bus)
        await uc.execute(42)

        mock_service.delete.assert_called_once_with(42)
        mock_event_bus.publish.assert_called_once_with(
            event_type="item.deleted",
            payload={"item_id": 42},
        )


class TestUpdateItemUseCase:
    async def test_delegates_to_service_and_publishes_event(self):
        mock_service = AsyncMock()
        mock_event_bus = AsyncMock()
        updated = MagicMock(spec=ItemORM)
        updated.id = 42
        updated.name = "New Name"
        mock_service.update.return_value = updated

        uc = UpdateItemUseCase(mock_service, mock_event_bus)
        result = await uc.execute(42, {"name": "New Name"})

        mock_service.update.assert_called_once_with(42, {"name": "New Name"})
        mock_event_bus.publish.assert_called_once_with(
            event_type="item.updated",
            payload={"item_id": 42, "name": "New Name", "changes": ["name"]},
        )
        assert result is updated


class TestListItemsUseCase:
    async def test_delegates_to_service(self):
        mock_service = AsyncMock()
        items = [MagicMock(spec=ItemORM)]
        mock_service.list_paginated.return_value = (items, 1)

        uc = ListItemsUseCase(mock_service)
        result = await uc.execute(
            page=2, page_size=10, order_by="name", order_dir="desc", filters={"category": "tools"}
        )

        mock_service.list_paginated.assert_called_once_with(
            page=2, page_size=10, order_by="name", order_dir="desc", filters={"category": "tools"}
        )
        assert result == (items, 1)


class TestListItemsCursorUseCase:
    async def test_delegates_to_service(self):
        mock_service = AsyncMock()
        items = [MagicMock(spec=ItemORM)]
        mock_service.list_cursor.return_value = (items, "next", True)

        uc = ListItemsCursorUseCase(mock_service)
        result = await uc.execute(
            cursor="abc", limit=5, order_by="id", order_dir="asc", filters=None
        )

        mock_service.list_cursor.assert_called_once_with(
            cursor="abc", limit=5, order_by="id", order_dir="asc", filters=None
        )
        assert result == (items, "next", True)
