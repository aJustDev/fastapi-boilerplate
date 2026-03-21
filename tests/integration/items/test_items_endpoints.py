from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.security import create_access_token
from app.models.auth.user import UserORM
from app.models.items.item import ItemORM
from main import app


@pytest.fixture
def fake_user() -> MagicMock:
    user = MagicMock(spec=UserORM)
    user.id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.full_name = "Test User"
    user.is_active = True
    user.roles = []
    user.has_role = MagicMock(return_value=False)
    user.has_permission = MagicMock(return_value=False)
    return user


@pytest.fixture
def auth_headers(fake_user: MagicMock) -> dict[str, str]:
    token = create_access_token(subject=str(fake_user.id), scopes=[])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_item() -> MagicMock:
    item = MagicMock(spec=ItemORM)
    item.id = 1
    item.name = "Test Item"
    item.description = "desc"
    item.category = "electronics"
    item.priority = 2
    item.is_active = True
    item.owner_id = 1
    item.created_at = datetime.now(UTC)
    item.updated_at = None
    item.owner = None
    return item


@pytest.fixture
async def client():
    mock_session = AsyncMock()

    async def _override():
        yield mock_session

    app.dependency_overrides[get_session] = _override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


class TestListItems:
    async def test_list_items_success(self, client, fake_user, fake_item, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.list", return_value=([fake_item], 1)),
        ):
            response = await client.get("/v1/items", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Test Item"

    async def test_list_items_cursor_success(self, client, fake_user, fake_item, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch(
                "app.repos.items.item.ItemRepo.list_cursor",
                return_value=([fake_item], None, False),
            ),
        ):
            response = await client.get("/v1/items/cursor", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "next_cursor" in data
        assert "has_more" in data
        assert data["has_more"] is False
        assert data["next_cursor"] is None
        assert len(data["items"]) == 1


class TestGetItem:
    async def test_get_item_success(self, client, fake_user, fake_item, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.get_by_id", return_value=fake_item),
        ):
            response = await client.get("/v1/items/1", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["name"] == "Test Item"
        assert data["category"] == "electronics"

    async def test_get_item_not_found(self, client, fake_user, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.get_by_id", return_value=None),
        ):
            response = await client.get("/v1/items/999", headers=auth_headers)

        assert response.status_code == 404


class TestCreateItem:
    async def test_create_item_success(self, client, fake_user, fake_item, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.create", return_value=fake_item),
        ):
            response = await client.post(
                "/v1/items",
                headers=auth_headers,
                json={
                    "name": "Test Item",
                    "description": "desc",
                    "category": "electronics",
                    "priority": 2,
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Item"
        assert data["owner_id"] == 1


class TestUpdateItem:
    async def test_patch_item_success(self, client, fake_user, fake_item, auth_headers):
        updated_item = MagicMock(spec=ItemORM)
        updated_item.id = 1
        updated_item.name = "Updated Item"
        updated_item.description = "desc"
        updated_item.category = "electronics"
        updated_item.priority = 2
        updated_item.is_active = True
        updated_item.owner_id = 1
        updated_item.created_at = datetime.now(UTC)
        updated_item.updated_at = datetime.now(UTC)
        updated_item.owner = None

        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.get_by_id", return_value=fake_item),
            patch("app.repos.items.item.ItemRepo.update", return_value=updated_item),
        ):
            response = await client.patch(
                "/v1/items/1",
                headers=auth_headers,
                json={"name": "Updated Item"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Item"


class TestDeleteItem:
    async def test_delete_item_success(self, client, fake_user, fake_item, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.get_by_id", return_value=fake_item),
            patch("app.repos.items.item.ItemRepo.delete", return_value=None),
        ):
            response = await client.delete("/v1/items/1", headers=auth_headers)

        assert response.status_code == 204

    async def test_delete_item_not_found(self, client, fake_user, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch("app.repos.items.item.ItemRepo.get_by_id", return_value=None),
        ):
            response = await client.delete("/v1/items/999", headers=auth_headers)

        assert response.status_code == 404


class TestFilterOptions:
    async def test_get_filter_options(self, client, fake_user, auth_headers):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=fake_user),
            patch(
                "app.repos.items.item.ItemRepo.get_distinct_categories",
                return_value=["electronics", "books"],
            ),
            patch(
                "app.repos.items.item.ItemRepo.get_distinct_priorities",
                return_value=[0, 1, 2],
            ),
        ):
            response = await client.get("/v1/items/filters", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "category" in data
        assert "priority" in data
        assert "is_active" in data
        assert data["category"] == ["electronics", "books"]
        assert data["priority"] == [0, 1, 2]
        assert data["is_active"] == [True, False]


class TestItemsAuth:
    async def test_endpoints_require_auth(self, client):
        response = await client.get("/v1/items")

        assert response.status_code == 401
