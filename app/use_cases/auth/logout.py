from dataclasses import dataclass

from app.services.auth import AuthService


@dataclass(slots=True)
class LogoutUseCase:
    auth_service: AuthService

    async def execute(self, token: str) -> None:
        await self.auth_service.logout(token)
