from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient

from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.auth.user import UserORM


def _user() -> MagicMock:
    user = MagicMock(spec=UserORM)
    user.id = 1
    user.is_active = True
    user.roles = []
    user.accepts_token_issued_at.return_value = True
    return user


class TestLogoutEndpoint:
    async def test_logout_revokes_the_refresh_token_too(self, client: AsyncClient):
        access = create_access_token(subject="1")
        refresh = create_refresh_token(subject="1")

        with patch(
            "app.repos.auth.revoked_token.RevokedTokenRepo.revoke", return_value=True
        ) as revoke:
            response = await client.post(
                "/v1/auth/logout",
                headers={"Authorization": f"Bearer {access}"},
                json={"refresh_token": refresh},
            )

        assert response.status_code == 204
        revoked = {str(call.args[0]) for call in revoke.call_args_list}
        assert revoked == {decode_token(access)["jti"], decode_token(refresh)["jti"]}

    async def test_logout_without_body_revokes_the_access_token(self, client: AsyncClient):
        access = create_access_token(subject="1")

        with patch(
            "app.repos.auth.revoked_token.RevokedTokenRepo.revoke", return_value=True
        ) as revoke:
            response = await client.post(
                "/v1/auth/logout", headers={"Authorization": f"Bearer {access}"}
            )

        assert response.status_code == 204
        assert revoke.call_count == 1


class TestRefreshEndpoint:
    async def test_replayed_refresh_token_is_rejected_and_ends_sessions(self, client: AsyncClient):
        own_session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=own_session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.repos.auth.user.UserRepo.get_by_id", return_value=_user()),
            patch("app.repos.auth.revoked_token.RevokedTokenRepo.revoke", return_value=False),
            patch("app.use_cases.auth.refresh_token.async_session_factory", factory),
            patch(
                "app.services.auth.AuthService.invalidate_sessions", new_callable=AsyncMock
            ) as invalidate,
        ):
            response = await client.post(
                "/v1/auth/refresh", json={"refresh_token": create_refresh_token(subject="1")}
            )

        assert response.status_code == 401
        invalidate.assert_called_once_with(1)
        own_session.commit.assert_called_once()
