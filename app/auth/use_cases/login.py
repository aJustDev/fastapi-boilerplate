from dataclasses import dataclass

from app.auth.schemas.token import TokenResponse
from app.auth.services.auth import AuthService


@dataclass(slots=True)
class LoginUseCase:
    auth_service: AuthService

    async def execute(self, username: str, password: str) -> TokenResponse:
        return await self.auth_service.login(username, password)
