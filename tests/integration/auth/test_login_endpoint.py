from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.db import get_session
from app.core.security import hash_password
from app.models.auth.user import UserORM
from main import app


@pytest.fixture
def active_user() -> MagicMock:
    user = MagicMock(spec=UserORM)
    user.id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    user.password_hash = hash_password("correct_password")
    user.roles = []
    return user


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


class TestLoginEndpoint:
    async def test_login_success(self, client, active_user):
        with patch("app.repos.auth.user.UserRepo.get_by_email", return_value=active_user):
            response = await client.post(
                "/v1/auth/login",
                data={"username": "test@example.com", "password": "correct_password"},
            )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_invalid_credentials(self, client):
        with (
            patch("app.repos.auth.user.UserRepo.get_by_email", return_value=None),
            patch("app.repos.auth.user.UserRepo.get_by_username", return_value=None),
        ):
            response = await client.post(
                "/v1/auth/login",
                data={"username": "nobody", "password": "wrong"},
            )

        assert response.status_code == 401

    async def test_login_missing_fields(self, client):
        response = await client.post("/v1/auth/login", data={})
        assert response.status_code == 422
