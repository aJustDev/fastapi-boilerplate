from unittest.mock import AsyncMock

from app.schemas.auth.token import TokenResponse
from app.use_cases.auth.login import LoginUseCase


class TestLoginUseCase:
    async def test_delegates_to_service(self):
        mock_service = AsyncMock()
        mock_service.login.return_value = TokenResponse(
            access_token="at", refresh_token="rt"
        )

        uc = LoginUseCase(mock_service)
        result = await uc.execute("user", "pass")

        mock_service.login.assert_called_once_with("user", "pass")
        assert result.access_token == "at"
        assert result.refresh_token == "rt"
