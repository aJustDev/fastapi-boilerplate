from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.schemas.token import TokenResponse
from app.auth.use_cases.refresh_token import RefreshTokenUseCase
from app.core.exceptions import RefreshTokenReuseError


class TestRefreshTokenUseCase:
    async def test_delegates_to_service(self):
        service = AsyncMock()
        service.refresh.return_value = TokenResponse(access_token="at", refresh_token="rt")

        result = await RefreshTokenUseCase(service).execute("rt-old")

        service.refresh.assert_called_once_with("rt-old")
        assert result.refresh_token == "rt"

    async def test_reuse_invalidates_sessions_in_its_own_transaction(self):
        service = AsyncMock()
        service.refresh.side_effect = RefreshTokenReuseError(user_id=7)
        own_session = AsyncMock()
        factory = MagicMock()
        factory.return_value.__aenter__ = AsyncMock(return_value=own_session)
        factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.auth.use_cases.refresh_token.async_session_factory", factory),
            patch("app.auth.use_cases.refresh_token.AuthService") as own_service_cls,
            pytest.raises(RefreshTokenReuseError),
        ):
            own_service_cls.return_value.invalidate_sessions = AsyncMock()
            await RefreshTokenUseCase(service).execute("stolen")

        own_service_cls.return_value.invalidate_sessions.assert_called_once_with(7)
        own_session.commit.assert_called_once()
