from dataclasses import dataclass

from app.models.auth.user import UserORM
from app.services.auth import AuthService


@dataclass(slots=True)
class RegisterUseCase:
    auth_service: AuthService

    async def execute(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str | None = None,
    ) -> UserORM:
        return await self.auth_service.register(email, username, password, full_name)
