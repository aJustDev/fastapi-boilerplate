from dataclasses import dataclass

from app.core.db import async_session_factory
from app.core.exceptions import RefreshTokenReuseError
from app.repos.auth.revoked_token import RevokedTokenRepo
from app.repos.auth.user import UserRepo
from app.schemas.auth.token import TokenResponse
from app.services.auth import AuthService


@dataclass(slots=True)
class RefreshTokenUseCase:
    auth_service: AuthService

    async def execute(self, refresh_token: str) -> TokenResponse:
        try:
            return await self.auth_service.refresh(refresh_token)
        except RefreshTokenReuseError as e:
            # The request ends in 401 and get_session rolls its transaction back, which
            # would undo the countermeasure too: it gets a transaction of its own.
            async with async_session_factory() as session:
                service = AuthService(UserRepo(session), RevokedTokenRepo(session))
                await service.invalidate_sessions(e.user_id)
                await session.commit()
            raise
