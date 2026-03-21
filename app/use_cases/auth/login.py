import logging
from dataclasses import dataclass

from app.schemas.auth.token import TokenResponse
from app.services.auth import AuthService

logger = logging.getLogger(__name__)

@dataclass(slots=True)
class LoginUseCase:
    auth_service: AuthService

    async def execute(self, username: str, password: str) -> TokenResponse:
        logger.info(f"Attempting login for user: {username}")
        return await self.auth_service.login(username, password)
