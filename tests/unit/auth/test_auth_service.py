from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from argon2 import PasswordHasher

from app.auth.models.user import UserORM
from app.auth.services.auth import AuthService
from app.core.exceptions import AuthenticationError, ConflictError, RefreshTokenReuseError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    verify_password,
)


@pytest.fixture
def user_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def revoked_token_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.is_revoked.return_value = False
    repo.revoke.return_value = True
    return repo


@pytest.fixture
def auth_service(user_repo: AsyncMock, revoked_token_repo: AsyncMock) -> AuthService:
    return AuthService(user_repo, revoked_token_repo)


@pytest.fixture
def active_user() -> MagicMock:
    user = MagicMock(spec=UserORM)
    user.id = 1
    user.email = "test@example.com"
    user.username = "testuser"
    user.is_active = True
    user.password_hash = hash_password("correct_password")
    user.roles = []
    user.session_version = 0
    user.accepts_session.return_value = True
    return user


class TestLogin:
    async def test_login_by_email_success(self, auth_service, user_repo, active_user):
        user_repo.get_by_email.return_value = active_user

        result = await auth_service.login("test@example.com", "correct_password")

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"

    async def test_login_upgrades_a_hash_made_with_older_parameters(
        self, auth_service, user_repo, active_user
    ):
        old = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("correct_password")
        active_user.password_hash = old
        user_repo.get_by_email.return_value = active_user

        await auth_service.login("test@example.com", "correct_password")

        assert active_user.password_hash != old
        assert not needs_rehash(active_user.password_hash)
        assert verify_password("correct_password", active_user.password_hash)

    async def test_login_keeps_a_current_hash(self, auth_service, user_repo, active_user):
        current = active_user.password_hash
        user_repo.get_by_email.return_value = active_user

        await auth_service.login("test@example.com", "correct_password")

        assert active_user.password_hash == current

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

    async def test_unknown_user_still_pays_a_password_check(self, auth_service, user_repo):
        # Without it, "no such account" answers faster than "wrong password".
        user_repo.get_by_email.return_value = None
        user_repo.get_by_username.return_value = None

        with (
            patch("app.auth.services.auth._verify_against_dummy") as dummy,
            pytest.raises(AuthenticationError),
        ):
            await auth_service.login("nobody@example.com", "secret")

        dummy.assert_called_once_with("secret")

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

    async def test_refresh_rotates_the_token(
        self, auth_service, user_repo, revoked_token_repo, active_user
    ):
        user_repo.get_by_id.return_value = active_user
        old = create_refresh_token(subject="1")

        result = await auth_service.refresh(old)

        revoked_jti = revoked_token_repo.revoke.call_args.args[0]
        assert str(revoked_jti) == decode_token(old)["jti"]
        assert decode_token(result.refresh_token)["jti"] != decode_token(old)["jti"]

    async def test_replayed_refresh_token_raises_reuse(
        self, auth_service, user_repo, revoked_token_repo, active_user
    ):
        user_repo.get_by_id.return_value = active_user
        revoked_token_repo.revoke.return_value = False  # already rotated

        with pytest.raises(RefreshTokenReuseError) as exc:
            await auth_service.refresh(create_refresh_token(subject="1"))

        assert exc.value.user_id == 1

    async def test_refresh_rejects_a_token_of_an_ended_session(
        self, auth_service, user_repo, active_user
    ):
        active_user.accepts_session.return_value = False
        user_repo.get_by_id.return_value = active_user

        with pytest.raises(AuthenticationError, match="invalidated"):
            await auth_service.refresh(create_refresh_token(subject="1", session_version=4))

        active_user.accepts_session.assert_called_once_with(4)

    async def test_new_tokens_carry_the_session_version_of_the_account(
        self, auth_service, user_repo, active_user
    ):
        active_user.session_version = 5
        user_repo.get_by_id.return_value = active_user

        result = await auth_service.refresh(create_refresh_token(subject="1", session_version=5))

        assert decode_token(result.access_token)["sv"] == 5
        assert decode_token(result.refresh_token)["sv"] == 5

    async def test_refresh_of_an_inactive_account_is_rejected(
        self, auth_service, user_repo, active_user
    ):
        active_user.is_active = False
        user_repo.get_by_id.return_value = active_user

        with pytest.raises(AuthenticationError, match="inactive"):
            await auth_service.refresh(create_refresh_token(subject="1"))

    async def test_access_token_is_not_a_refresh_token(self, auth_service):
        with pytest.raises(AuthenticationError, match="not a refresh token"):
            await auth_service.refresh(create_access_token(subject="1"))


class TestLogout:
    async def test_revokes_access_and_refresh(self, auth_service, revoked_token_repo):
        access = create_access_token(subject="1")
        refresh = create_refresh_token(subject="1")

        await auth_service.logout(access, refresh)

        revoked = {str(call.args[0]) for call in revoked_token_repo.revoke.call_args_list}
        assert revoked == {decode_token(access)["jti"], decode_token(refresh)["jti"]}

    async def test_refresh_of_another_user_is_rejected(self, auth_service):
        with pytest.raises(AuthenticationError, match="another user"):
            await auth_service.logout(
                create_access_token(subject="1"), create_refresh_token(subject="2")
            )


class TestInvalidateSessions:
    async def test_ends_the_sessions_of_that_user(self, auth_service, user_repo):
        await auth_service.invalidate_sessions(1)

        user_repo.end_sessions.assert_called_once_with(1)
