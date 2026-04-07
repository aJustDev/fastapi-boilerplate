import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_token
from app.deps.repository import get_repo
from app.models.auth.user import UserORM
from app.repos.auth.revoked_token import RevokedTokenRepo
from app.repos.auth.user import UserRepo

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/v1/auth/login")


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    user_repo: Annotated[UserRepo, Depends(get_repo(UserRepo))],
    revoked_token_repo: Annotated[RevokedTokenRepo, Depends(get_repo(RevokedTokenRepo))],
) -> UserORM:
    try:
        payload = decode_token(token)
    except Exception as e:
        raise AuthenticationError("Invalid or expired token") from e

    if payload.get("type") != "access":
        raise AuthenticationError("Token is not an access token")

    jti = payload.get("jti")
    if not jti:
        raise AuthenticationError("Invalid token payload")

    if await revoked_token_repo.is_revoked(uuid.UUID(jti)):
        raise AuthenticationError("Token has been revoked")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid token payload")

    user = await user_repo.get_by_id(int(user_id))
    if not user:
        raise AuthenticationError("User not found")

    if not user.is_active:
        raise AuthenticationError("Account is inactive")

    return user


CurrentUser = Annotated[UserORM, Depends(get_current_user)]


def require_permissions(
    *,
    role: str | None = None,
    permission: str | None = None,
):
    """Returns a dependency that validates the user has the required role/permission."""

    async def _check(user: CurrentUser) -> UserORM:
        if role and not user.has_role(role):
            raise AuthorizationError(f"Role '{role}' required")
        if permission and not user.has_permission(permission):
            raise AuthorizationError(f"Permission '{permission}' required")
        return user

    return _check
