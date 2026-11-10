from dataclasses import dataclass

from app.services.auth import AuthService


@dataclass(slots=True)
class LogoutUseCase:
    auth_service: AuthService

    async def execute(self, access_token: str, refresh_token: str | None = None) -> None:
        await self.auth_service.logout(access_token, refresh_token)
