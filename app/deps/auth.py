import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer

from app.auth.models.user import UserORM
from app.auth.repos.revoked_token import RevokedTokenRepo
from app.auth.repos.user import UserRepo
from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.logging.context import actor_var
from app.core.security import decode_token
from app.deps.repository import get_repo

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

    if not user.accepts_session(payload["sv"]):
        raise AuthenticationError("Session has been invalidated")

    # From here on, rows written by this request record who wrote them (AuditMixin).
    actor_var.set(str(user.id))
    return user


CurrentUser = Annotated[UserORM, Depends(get_current_user)]

# The user type, for contexts that declare their own guarded dependencies
# (`Annotated[User, Depends(require_permissions(...))]`) without importing app.auth.
User = UserORM


def require_permissions(
    *,
    role: str | None = None,
    permission: str | None = None,
) -> Callable[[UserORM], Awaitable[UserORM]]:
    """Returns a dependency that validates the user has the required role/permission.

    It answers 403 (`forbidden`) and returns the user. This is the function-level check:
    whether the user may do this kind of thing at all. Whether it may do it to this
    particular resource is decided by the use case (see app/items/services/access.py).
    """

    async def _check(user: CurrentUser) -> UserORM:
        if role and not user.has_role(role):
            raise AuthorizationError(f"Role '{role}' required")
        if permission and not user.has_permission(permission):
            raise AuthorizationError(f"Permission '{permission}' required")
        return user

    return _check
