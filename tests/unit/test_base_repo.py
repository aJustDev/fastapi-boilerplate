from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import Text, asc, desc
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.repos.base import BaseRepo, decode_cursor, encode_cursor


class FakeModel(Base):
    __tablename__ = "fake"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    priority: Mapped[int] = mapped_column()


class FakeRepo(BaseRepo[FakeModel]):
    model = FakeModel
    map_field = {
        "name": {"column": FakeModel.name, "op": "ilike"},
        "priority": {"column": FakeModel.priority, "op": "eq"},
    }


class TestEncodeDecode:
    def test_roundtrip_simple(self):
        data = {"id": 42, "name": "hello"}
        cursor = encode_cursor(data)
        assert isinstance(cursor, str)
        result = decode_cursor(cursor)
        assert result == data

    def test_roundtrip_with_special_chars(self):
        data = {"id": 1, "value": "hello world / + ="}
        assert decode_cursor(encode_cursor(data)) == data

    def test_roundtrip_numeric_values(self):
        data = {"id": 99, "priority": 5}
        assert decode_cursor(encode_cursor(data)) == data


class TestBaseRepoCRUD:
    def _make_repo(self, session: AsyncMock) -> FakeRepo:
        return FakeRepo(session)

    async def test_create(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        entity = MagicMock(spec=FakeModel)

        result = await repo.create(entity)

        mock_session.add.assert_called_once_with(entity)
        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(entity)
        assert result is entity

    async def test_get_by_id_found(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        fake_item = MagicMock(spec=FakeModel)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = fake_item
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(1)

        assert result is fake_item
        mock_session.execute.assert_awaited_once()

    async def test_get_by_id_not_found(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_result

        result = await repo.get_by_id(999)

        assert result is None

    async def test_update(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        entity = MagicMock(spec=FakeModel)
        entity.name = "old"
        entity.priority = 0

        result = await repo.update(entity, {"name": "new", "priority": 5})

        mock_session.flush.assert_awaited_once()
        mock_session.refresh.assert_awaited_once_with(entity)
        assert result is entity

    async def test_update_ignores_unknown_attrs(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        entity = MagicMock(spec=FakeModel)
        entity.name = "old"

        # hasattr on MagicMock with spec will return False for unknown attrs
        await repo.update(entity, {"nonexistent_field": "value"})

        mock_session.flush.assert_awaited_once()

    async def test_delete(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        entity = MagicMock(spec=FakeModel)

        await repo.delete(entity)

        mock_session.delete.assert_awaited_once_with(entity)
        mock_session.flush.assert_awaited_once()


class TestBaseRepoList:
    def _make_repo(self, session: AsyncMock) -> FakeRepo:
        return FakeRepo(session)

    async def test_list_returns_items_and_total(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        fake_items = [MagicMock(spec=FakeModel), MagicMock(spec=FakeModel)]

        # session.execute is called twice: once for count, once for items
        count_result = MagicMock()
        count_result.scalar.return_value = 2

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = fake_items

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repo.list_paginated(page=1, page_size=20)

        assert items == fake_items
        assert total == 2
        assert mock_session.execute.await_count == 2

    async def test_list_with_page_and_page_size(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)

        count_result = MagicMock()
        count_result.scalar.return_value = 50

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [MagicMock()] * 10

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repo.list_paginated(page=3, page_size=10)

        assert total == 50
        assert len(items) == 10

    async def test_list_total_zero(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)

        count_result = MagicMock()
        count_result.scalar.return_value = None  # triggers `or 0`

        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [count_result, items_result]

        items, total = await repo.list_paginated()

        assert total == 0
        assert items == []


class TestBaseRepoListCursor:
    def _make_repo(self, session: AsyncMock) -> FakeRepo:
        return FakeRepo(session)

    async def test_has_more_true(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        # Return limit+1 items to signal has_more
        fake_items = []
        for i in range(4):
            item = MagicMock(spec=FakeModel)
            item.id = i + 1
            fake_items.append(item)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = fake_items

        mock_session.execute.return_value = result_mock

        items, next_cursor, has_more = await repo.list_cursor(limit=3)

        assert has_more is True
        assert len(items) == 3
        assert next_cursor is not None

    async def test_has_more_false(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        fake_items = []
        for i in range(2):
            item = MagicMock(spec=FakeModel)
            item.id = i + 1
            fake_items.append(item)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = fake_items

        mock_session.execute.return_value = result_mock

        items, next_cursor, has_more = await repo.list_cursor(limit=3)

        assert has_more is False
        assert len(items) == 2
        assert next_cursor is None

    async def test_next_cursor_is_base64(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        fake_items = []
        for i in range(4):
            item = MagicMock(spec=FakeModel)
            item.id = i + 1
            fake_items.append(item)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = fake_items

        mock_session.execute.return_value = result_mock

        _, next_cursor, _ = await repo.list_cursor(limit=3)

        decoded = decode_cursor(next_cursor)
        assert "id" in decoded
        assert decoded["id"] == 3  # last item in truncated list

    async def test_empty_result(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []

        mock_session.execute.return_value = result_mock

        items, next_cursor, has_more = await repo.list_cursor(limit=20)

        assert items == []
        assert next_cursor is None
        assert has_more is False

    async def test_cursor_includes_sort_field(self, mock_session: AsyncMock):
        repo = self._make_repo(mock_session)
        fake_items = []
        for i in range(4):
            item = MagicMock(spec=FakeModel)
            item.id = i + 1
            item.name = f"item_{i}"
            fake_items.append(item)

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = fake_items

        mock_session.execute.return_value = result_mock

        _, next_cursor, _ = await repo.list_cursor(limit=3, order_by="name")

        decoded = decode_cursor(next_cursor)
        assert "id" in decoded
        assert "name" in decoded


class TestResolveSort:
    def _make_repo(self) -> FakeRepo:
        return FakeRepo(AsyncMock())

    def test_default_no_order_by(self):
        repo = self._make_repo()
        column, field_name, direction = repo._resolve_sort(None, "asc")

        assert field_name == "id"
        assert direction is asc

    def test_order_by_id(self):
        repo = self._make_repo()
        column, field_name, direction = repo._resolve_sort("id", "asc")

        assert field_name == "id"

    def test_mapped_field(self):
        repo = self._make_repo()
        column, field_name, direction = repo._resolve_sort("name", "asc")

        assert field_name == "name"
        assert direction is asc

    def test_model_attribute(self):
        repo = self._make_repo()
        # "priority" is both in map_field and model; map_field takes precedence
        column, field_name, direction = repo._resolve_sort("priority", "desc")

        assert field_name == "priority"
        assert direction is desc

    def test_unknown_field_falls_back_to_id(self):
        repo = self._make_repo()
        column, field_name, direction = repo._resolve_sort("nonexistent", "asc")

        assert field_name == "id"

    def test_desc_direction(self):
        repo = self._make_repo()
        _, _, direction = repo._resolve_sort(None, "desc")

        assert direction is desc

    def test_asc_direction(self):
        repo = self._make_repo()
        _, _, direction = repo._resolve_sort(None, "asc")

        assert direction is asc
