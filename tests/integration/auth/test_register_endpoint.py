from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.models.auth.user import UserORM
from main import app


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


class TestRegisterEndpoint:
    async def test_register_success(self, client):
        new_user = MagicMock(spec=UserORM)
        new_user.id = 1
        new_user.email = "new@example.com"
        new_user.username = "newuser"
        new_user.full_name = "New User"
        new_user.is_active = True
        new_user.created_at = "2024-01-01T00:00:00"
        new_user.roles = []

        with (
            patch("app.repos.auth.user.UserRepo.get_by_email", return_value=None),
            patch("app.repos.auth.user.UserRepo.get_by_username", return_value=None),
            patch("app.repos.auth.user.UserRepo.create", return_value=new_user),
        ):
            response = await client.post(
                "/v1/auth/register",
                json={
                    "email": "new@example.com",
                    "username": "newuser",
                    "password": "securepass123",
                    "full_name": "New User",
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "new@example.com"
        assert data["username"] == "newuser"

    async def test_register_duplicate_email(self, client):
        existing = MagicMock(spec=UserORM)

        with patch("app.repos.auth.user.UserRepo.get_by_email", return_value=existing):
            response = await client.post(
                "/v1/auth/register",
                json={
                    "email": "existing@example.com",
                    "username": "newuser",
                    "password": "pass123",
                },
            )

        assert response.status_code == 409
