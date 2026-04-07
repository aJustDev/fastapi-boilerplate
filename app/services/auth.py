import logging
import uuid
from datetime import datetime

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.auth.user import UserORM
from app.repos.auth.revoked_token import RevokedTokenRepo
from app.repos.auth.user import UserRepo
from app.schemas.auth.token import TokenResponse

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, user_repo: UserRepo, revoked_token_repo: RevokedTokenRepo):
        self.user_repo = user_repo
        self.revoked_token_repo = revoked_token_repo

    async def login(self, username: str, password: str) -> TokenResponse:
        logger.debug("Looking up user credentials")
        user = await self.user_repo.get_by_email(username)
        if not user:
            user = await self.user_repo.get_by_username(username)

        logger.debug("User lookup result: %s", "found" if user else "not found")
        if not user or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid credentials")

        if not user.is_active:
            raise AuthenticationError("Account is inactive")

        return self._generate_tokens(user)

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str | None = None,
    ) -> UserORM:
        if await self.user_repo.get_by_email(email):
            raise ConflictError("User", "email already registered")

        if await self.user_repo.get_by_username(username):
            raise ConflictError("User", "username already taken")

        user = UserORM(
            email=email,
            username=username,
            password_hash=hash_password(password),
            full_name=full_name,
            is_active=True,
        )
        return await self.user_repo.create(user)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except Exception as e:
            raise AuthenticationError("Invalid refresh token") from e

        if payload.get("type") != "refresh":
            raise AuthenticationError("Token is not a refresh token")

        jti = payload.get("jti")
        if jti and await self.revoked_token_repo.is_revoked(uuid.UUID(jti)):
            raise AuthenticationError("Refresh token has been revoked")

        user_id = payload["sub"]
        user = await self.user_repo.get_by_id(int(user_id))
        if not user:
            raise AuthenticationError("User not found")

        if not user.is_active:
            raise AuthenticationError("Account is inactive")

        return self._generate_tokens(user)

    async def logout(self, jti: str, expires_at: datetime) -> None:
        await self.revoked_token_repo.revoke(uuid.UUID(jti), expires_at)

    def _generate_tokens(self, user: UserORM) -> TokenResponse:
        role_names = [r.name for r in user.roles]
        access_token = create_access_token(subject=str(user.id), scopes=role_names)
        refresh_token = create_refresh_token(subject=str(user.id))
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
