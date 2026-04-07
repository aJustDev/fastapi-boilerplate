from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import create_access_token, create_refresh_token
from app.deps.auth import get_current_user, require_permissions
from app.models.auth.user import UserORM


def _revoked_token_repo(is_revoked: bool = False) -> AsyncMock:
    repo = AsyncMock()
    repo.is_revoked.return_value = is_revoked
    return repo


class TestGetCurrentUser:
    async def test_valid_access_token_returns_user(self, fake_user: UserORM):
        token = create_access_token(subject=str(fake_user.id))
        user_repo = AsyncMock()
        user_repo.get_by_id.return_value = fake_user

        result = await get_current_user(
            token=token, user_repo=user_repo, revoked_token_repo=_revoked_token_repo()
        )

        assert result is fake_user
        user_repo.get_by_id.assert_awaited_once_with(fake_user.id)

    async def test_invalid_token_raises_authentication_error(self):
        user_repo = AsyncMock()

        with pytest.raises(AuthenticationError, match="Invalid or expired token"):
            await get_current_user(
                token="invalid.jwt.token",
                user_repo=user_repo,
                revoked_token_repo=_revoked_token_repo(),
            )

    async def test_refresh_token_raises_authentication_error(self, fake_user: UserORM):
        token = create_refresh_token(subject=str(fake_user.id))
        user_repo = AsyncMock()

        with pytest.raises(AuthenticationError, match="Token is not an access token"):
            await get_current_user(
                token=token, user_repo=user_repo, revoked_token_repo=_revoked_token_repo()
            )

    async def test_missing_sub_raises_authentication_error(self):
        """A token without sub should fail at decode_token (sub is required)."""
        import jwt as pyjwt

        from app.core.config import settings

        token = pyjwt.encode(
            {"exp": 9999999999, "iat": 1000000000, "type": "access"},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        user_repo = AsyncMock()

        with pytest.raises(AuthenticationError):
            await get_current_user(
                token=token, user_repo=user_repo, revoked_token_repo=_revoked_token_repo()
            )

    async def test_user_not_found_raises_authentication_error(self):
        token = create_access_token(subject="999")
        user_repo = AsyncMock()
        user_repo.get_by_id.return_value = None

        with pytest.raises(AuthenticationError, match="User not found"):
            await get_current_user(
                token=token, user_repo=user_repo, revoked_token_repo=_revoked_token_repo()
            )

    async def test_inactive_user_raises_authentication_error(self):
        user = MagicMock(spec=UserORM)
        user.id = 1
        user.is_active = False

        token = create_access_token(subject="1")
        user_repo = AsyncMock()
        user_repo.get_by_id.return_value = user

        with pytest.raises(AuthenticationError, match="Account is inactive"):
            await get_current_user(
                token=token, user_repo=user_repo, revoked_token_repo=_revoked_token_repo()
            )

    async def test_revoked_token_raises_authentication_error(self, fake_user: UserORM):
        token = create_access_token(subject=str(fake_user.id))
        user_repo = AsyncMock()

        with pytest.raises(AuthenticationError, match="Token has been revoked"):
            await get_current_user(
                token=token,
                user_repo=user_repo,
                revoked_token_repo=_revoked_token_repo(is_revoked=True),
            )


class TestRequirePermissions:
    async def test_role_check_passes(self, fake_user: UserORM):
        fake_user.has_role.return_value = True
        checker = require_permissions(role="admin")

        result = await checker(user=fake_user)

        assert result is fake_user
        fake_user.has_role.assert_called_once_with("admin")

    async def test_role_check_fails(self, fake_user: UserORM):
        fake_user.has_role.return_value = False
        checker = require_permissions(role="admin")

        with pytest.raises(AuthorizationError, match="Role 'admin' required"):
            await checker(user=fake_user)

    async def test_permission_check_passes(self, fake_user: UserORM):
        fake_user.has_permission.return_value = True
        checker = require_permissions(permission="items:write")

        result = await checker(user=fake_user)

        assert result is fake_user
        fake_user.has_permission.assert_called_once_with("items:write")

    async def test_permission_check_fails(self, fake_user: UserORM):
        fake_user.has_permission.return_value = False
        checker = require_permissions(permission="items:write")

        with pytest.raises(AuthorizationError, match="Permission 'items:write' required"):
            await checker(user=fake_user)

    async def test_no_role_or_permission_passes(self, fake_user: UserORM):
        checker = require_permissions()

        result = await checker(user=fake_user)

        assert result is fake_user
