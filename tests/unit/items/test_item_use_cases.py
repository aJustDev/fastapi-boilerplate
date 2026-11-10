from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import NotFoundError
from app.items.models.item import ItemORM
from app.items.services.access import Actor
from app.items.use_cases.create_item import CreateItemUseCase
from app.items.use_cases.delete_item import DeleteItemUseCase
from app.items.use_cases.get_filter_options import GetFilterOptionsUseCase
from app.items.use_cases.get_item import GetItemUseCase
from app.items.use_cases.list_items import ListItemsCursorUseCase, ListItemsUseCase
from app.items.use_cases.update_item import UpdateItemUseCase

OWNER = Actor(user_id=1, manages_all=False)
STRANGER = Actor(user_id=2, manages_all=False)
MANAGER = Actor(user_id=3, manages_all=True)


def _item(owner_id: int = 1) -> MagicMock:
    item = MagicMock(spec=ItemORM)
    item.id = 10
    item.name = "Test Item"
    item.owner_id = owner_id
    return item


class TestCreateItemUseCase:
    async def test_create_builds_orm_and_publishes_event(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        created_item = _item()
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
        assert mock_event_bus.publish.call_args.kwargs["event_type"] == "item.created"

    async def test_create_uses_defaults(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        mock_repo.create.return_value = _item()
        uc = CreateItemUseCase(mock_repo, mock_event_bus)

        await uc.execute(name="Item", owner_id=1)

        call_arg = mock_repo.create.call_args[0][0]
        assert call_arg.category == "general"
        assert call_arg.priority == 0


class TestGetItemUseCase:
    async def test_owner_gets_the_item(self):
        mock_repo = AsyncMock()
        item = _item(owner_id=1)
        mock_repo.get_by_id.return_value = item

        assert await GetItemUseCase(mock_repo).execute(10, OWNER) is item
        mock_repo.get_by_id.assert_awaited_once_with(10)

    async def test_missing_item(self):
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None

        with pytest.raises(NotFoundError, match="Item not found"):
            await GetItemUseCase(mock_repo).execute(999, OWNER)

    async def test_someone_elses_item_looks_missing(self):
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = _item(owner_id=1)

        with pytest.raises(NotFoundError, match="Item not found"):
            await GetItemUseCase(mock_repo).execute(10, STRANGER)

    async def test_manager_gets_any_item(self):
        mock_repo = AsyncMock()
        item = _item(owner_id=1)
        mock_repo.get_by_id.return_value = item

        assert await GetItemUseCase(mock_repo).execute(10, MANAGER) is item


class TestUpdateItemUseCase:
    async def test_update_and_publishes_event(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        existing_item = _item(owner_id=1)
        updated_item = MagicMock(spec=ItemORM, id=10, name="Updated")
        mock_repo.get_by_id.return_value = existing_item
        mock_repo.update.return_value = updated_item
        uc = UpdateItemUseCase(mock_repo, mock_event_bus)

        result = await uc.execute(10, {"name": "Updated"}, OWNER)

        assert result is updated_item
        mock_repo.update.assert_awaited_once_with(existing_item, {"name": "Updated"})
        mock_event_bus.publish.assert_awaited_once()
        published = mock_event_bus.publish.call_args.kwargs
        assert published["event_type"] == "item.updated"
        assert published["payload"]["changes"] == ["name"]

    async def test_someone_elses_item_is_not_touched(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        mock_repo.get_by_id.return_value = _item(owner_id=1)
        uc = UpdateItemUseCase(mock_repo, mock_event_bus)

        with pytest.raises(NotFoundError):
            await uc.execute(10, {"name": "Updated"}, STRANGER)

        mock_repo.update.assert_not_awaited()
        mock_event_bus.publish.assert_not_awaited()


class TestDeleteItemUseCase:
    async def test_delete_and_publishes_event(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        existing_item = _item(owner_id=1)
        mock_repo.get_by_id.return_value = existing_item
        uc = DeleteItemUseCase(mock_repo, mock_event_bus)

        await uc.execute(10, OWNER)

        mock_repo.delete.assert_awaited_once_with(existing_item)
        mock_event_bus.publish.assert_awaited_once()
        assert mock_event_bus.publish.call_args.kwargs["payload"] == {"item_id": 10}

    async def test_delete_not_found(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        mock_repo.get_by_id.return_value = None
        uc = DeleteItemUseCase(mock_repo, mock_event_bus)

        with pytest.raises(NotFoundError):
            await uc.execute(999, OWNER)

    async def test_someone_elses_item_is_not_deleted(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        mock_repo.get_by_id.return_value = _item(owner_id=1)
        uc = DeleteItemUseCase(mock_repo, mock_event_bus)

        with pytest.raises(NotFoundError):
            await uc.execute(10, STRANGER)

        mock_repo.delete.assert_not_awaited()
        mock_event_bus.publish.assert_not_awaited()

    async def test_manager_deletes_any_item(self):
        mock_repo = AsyncMock()
        mock_event_bus = AsyncMock()
        existing_item = _item(owner_id=1)
        mock_repo.get_by_id.return_value = existing_item

        await DeleteItemUseCase(mock_repo, mock_event_bus).execute(10, MANAGER)

        mock_repo.delete.assert_awaited_once_with(existing_item)


class TestListItemsUseCase:
    async def test_a_user_lists_only_its_own_items(self):
        mock_repo = AsyncMock()
        items = [_item()]
        mock_repo.list_paginated.return_value = (items, 1)
        uc = ListItemsUseCase(mock_repo)

        result = await uc.execute(
            OWNER,
            page=2,
            page_size=10,
            order_by="name",
            order_dir="desc",
            filters={"category": "tools"},
        )

        assert result == (items, 1)
        mock_repo.list_paginated.assert_awaited_once_with(
            page=2,
            page_size=10,
            order_by="name",
            order_dir="desc",
            filters={"category": "tools", "owner_id": 1},
        )

    async def test_the_owner_scope_cannot_be_overridden_by_a_filter(self):
        mock_repo = AsyncMock()
        mock_repo.list_paginated.return_value = ([], 0)

        await ListItemsUseCase(mock_repo).execute(STRANGER, filters={"owner_id": 1})

        assert mock_repo.list_paginated.call_args.kwargs["filters"]["owner_id"] == 2

    async def test_a_manager_lists_every_owner(self):
        mock_repo = AsyncMock()
        mock_repo.list_paginated.return_value = ([], 0)

        await ListItemsUseCase(mock_repo).execute(MANAGER, filters=None)

        # None is "no filter" for the repository.
        assert mock_repo.list_paginated.call_args.kwargs["filters"] == {"owner_id": None}


class TestListItemsCursorUseCase:
    async def test_a_user_pages_only_through_its_own_items(self):
        mock_repo = AsyncMock()
        items = [_item()]
        mock_repo.list_cursor.return_value = (items, "next_cursor", True)
        uc = ListItemsCursorUseCase(mock_repo)

        result = await uc.execute(
            OWNER, cursor="abc", limit=10, order_by="id", order_dir="asc", filters=None
        )

        assert result == (items, "next_cursor", True)
        mock_repo.list_cursor.assert_awaited_once_with(
            cursor="abc", limit=10, order_by="id", order_dir="asc", filters={"owner_id": 1}
        )


class TestGetFilterOptionsUseCase:
    async def test_options_come_from_the_items_the_actor_sees(self):
        mock_repo = AsyncMock()
        mock_repo.get_distinct_categories.return_value = ["books"]
        mock_repo.get_distinct_priorities.return_value = [1, 2]

        options = await GetFilterOptionsUseCase(mock_repo).execute(OWNER)

        assert options.category == ["books"]
        assert options.priority == [1, 2]
        assert options.is_active == [True, False]
        mock_repo.get_distinct_categories.assert_awaited_once_with(1)
        mock_repo.get_distinct_priorities.assert_awaited_once_with(1)

    async def test_a_manager_gets_the_options_of_every_owner(self):
        mock_repo = AsyncMock()
        mock_repo.get_distinct_categories.return_value = []
        mock_repo.get_distinct_priorities.return_value = []

        await GetFilterOptionsUseCase(mock_repo).execute(MANAGER)

        mock_repo.get_distinct_categories.assert_awaited_once_with(None)
