from dataclasses import dataclass

from app.schemas.auth.token import TokenResponse
from app.services.auth import AuthService


@dataclass(slots=True)
class RefreshTokenUseCase:
    auth_service: AuthService

    async def execute(self, refresh_token: str) -> TokenResponse:
        return await self.auth_service.refresh(refresh_token)
