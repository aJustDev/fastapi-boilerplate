import functools
import logging
import uuid
from datetime import UTC, datetime

from app.auth.models.user import UserORM
from app.auth.repos.revoked_token import RevokedTokenRepo
from app.auth.repos.user import UserRepo
from app.auth.schemas.token import TokenResponse
from app.core.concurrency import run_blocking
from app.core.exceptions import AuthenticationError, ConflictError, RefreshTokenReuseError
from app.core.security import (
    TokenPayload,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

logger = logging.getLogger(__name__)


@functools.cache
def _dummy_hash() -> str:
    return hash_password("dummy-password-for-timing")


def _verify_against_dummy(password: str) -> None:
    verify_password(password, _dummy_hash())


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
        if not user:
            # Same argon2 cost as a real check: otherwise the response time tells
            # whether the account exists.
            await run_blocking(_verify_against_dummy, password)
            raise AuthenticationError("Invalid credentials")
        if not await run_blocking(verify_password, password, user.password_hash):
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
            password_hash=await run_blocking(hash_password, password),
            full_name=full_name,
            is_active=True,
        )
        return await self.user_repo.create(user)

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Rotate a refresh token: the one presented is revoked and a new pair is issued.

        A refresh token that was already rotated raises RefreshTokenReuseError: only the
        legitimate client or a thief can hold it, and the use case ends every session.
        """
        payload = self._decode(refresh_token, "refresh")
        user = await self._active_user(payload)

        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        if not await self.revoked_token_repo.revoke(uuid.UUID(payload["jti"]), expires_at):
            logger.warning("Revoked refresh token replayed for user %s", user.id)
            raise RefreshTokenReuseError(user.id)

        return self._generate_tokens(user)

    async def logout(self, access_token: str, refresh_token: str | None = None) -> None:
        """Revoke the access token and, if given, the refresh token of the same user."""
        access = self._decode(access_token, "access")
        await self._revoke(access)

        if refresh_token is not None:
            refresh = self._decode(refresh_token, "refresh")
            if refresh["sub"] != access["sub"]:
                raise AuthenticationError("Refresh token belongs to another user")
            await self._revoke(refresh)

    async def invalidate_sessions(self, user_id: int) -> datetime:
        """Reject every token of the user issued until now.

        Truncated to the second because `iat` is an integer: a token issued later in the
        same second must stay valid.
        """
        at = datetime.now(UTC).replace(microsecond=0)
        await self.user_repo.invalidate_tokens(user_id, at)
        return at

    @staticmethod
    def _decode(token: str, expected_type: str) -> TokenPayload:
        try:
            payload = decode_token(token)
        except Exception as e:
            raise AuthenticationError(f"Invalid {expected_type} token") from e
        if payload.get("type") != expected_type:
            raise AuthenticationError(f"Token is not a {expected_type} token")
        return payload

    async def _active_user(self, payload: TokenPayload) -> UserORM:
        user = await self.user_repo.get_by_id(int(payload["sub"]))
        if not user:
            raise AuthenticationError("User not found")
        if not user.is_active:
            raise AuthenticationError("Account is inactive")
        if not user.accepts_token_issued_at(payload["iat"]):
            raise AuthenticationError("Session has been invalidated")
        return user

    async def _revoke(self, payload: TokenPayload) -> None:
        expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
        await self.revoked_token_repo.revoke(uuid.UUID(payload["jti"]), expires_at)

    def _generate_tokens(self, user: UserORM) -> TokenResponse:
        role_names = [r.name for r in user.roles]
        access_token = create_access_token(subject=str(user.id), scopes=role_names)
        refresh_token = create_refresh_token(subject=str(user.id))
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
