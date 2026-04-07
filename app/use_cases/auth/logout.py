from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.exceptions import AuthenticationError
from app.core.security import decode_token
from app.services.auth import AuthService


@dataclass(slots=True)
class LogoutUseCase:
    auth_service: AuthService

    async def execute(self, token: str) -> None:
        try:
            payload = decode_token(token)
        except Exception as e:
            raise AuthenticationError("Invalid token") from e

        jti = payload.get("jti")
        if not jti:
            raise AuthenticationError("Token missing jti claim")

        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        await self.auth_service.logout(jti, expires_at)
