from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import hash_password
from app.models.auth.user import UserORM
from app.services.auth import AuthService


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def auth_service(user_repo: AsyncMock) -> AuthService:
    return AuthService(user_repo)


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


class TestLogin:
    async def test_login_by_email_success(self, auth_service, user_repo, active_user):
        user_repo.get_by_email.return_value = active_user

        result = await auth_service.login("test@example.com", "correct_password")

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    async def test_login_by_username_success(self, auth_service, user_repo, active_user):
        user_repo.get_by_email.return_value = None
        user_repo.get_by_username.return_value = active_user

        result = await auth_service.login("testuser", "correct_password")
        assert result.access_token

    async def test_login_invalid_credentials(self, auth_service, user_repo):
        user_repo.get_by_email.return_value = None
        user_repo.get_by_username.return_value = None

        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await auth_service.login("nobody@example.com", "wrong")

    async def test_login_wrong_password(self, auth_service, user_repo, active_user):
        user_repo.get_by_email.return_value = active_user

        with pytest.raises(AuthenticationError, match="Invalid credentials"):
            await auth_service.login("test@example.com", "wrong_password")

    async def test_login_inactive_user(self, auth_service, user_repo, active_user):
        active_user.is_active = False
        user_repo.get_by_email.return_value = active_user

        with pytest.raises(AuthenticationError, match="inactive"):
            await auth_service.login("test@example.com", "correct_password")


class TestRegister:
    async def test_register_success(self, auth_service, user_repo):
        user_repo.get_by_email.return_value = None
        user_repo.get_by_username.return_value = None
        user_repo.create.return_value = MagicMock(spec=UserORM, id=1)

        result = await auth_service.register("new@example.com", "newuser", "pass123", "New User")

        user_repo.create.assert_called_once()
        assert result.id == 1

    async def test_register_duplicate_email(self, auth_service, user_repo, active_user):
        user_repo.get_by_email.return_value = active_user

        with pytest.raises(ConflictError, match="email"):
            await auth_service.register("test@example.com", "newuser", "pass123")

    async def test_register_duplicate_username(self, auth_service, user_repo, active_user):
        user_repo.get_by_email.return_value = None
        user_repo.get_by_username.return_value = active_user

        with pytest.raises(ConflictError, match="username"):
            await auth_service.register("new@example.com", "testuser", "pass123")


class TestRefresh:
    async def test_refresh_invalid_token(self, auth_service):
        with pytest.raises(AuthenticationError, match="Invalid refresh token"):
            await auth_service.refresh("bad.token.here")
