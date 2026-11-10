import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict, cast

import jwt

from app.core.config import settings

# Clock skew tolerated when checking `exp`. Whatever keeps a list of revoked tokens has to
# keep each entry this much longer than the token's `exp`.
JWT_LEEWAY_SECONDS = 30


class TokenPayload(TypedDict):
    sub: str
    exp: float
    iat: float
    type: str
    sv: int
    jti: str


def _encode(subject: str, token_type: str, session_version: int, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        # Session version of the account when the token was issued: a token is accepted
        # only while it matches the stored one (see UserORM.accepts_session).
        "sv": session_version,
        "exp": now + lifetime,
        "iat": now,
        "type": token_type,
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(subject: str, session_version: int = 0) -> str:
    return _encode(
        subject,
        "access",
        session_version,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(subject: str, session_version: int = 0) -> str:
    return _encode(
        subject,
        "refresh",
        session_version,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token. Raises jwt.PyJWTError on failure."""
    payload = jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={"require": ["exp", "iat", "sub", "jti", "sv"], "verify_iat": True},
        # An argument, not an option: PyJWT ignores a "leeway" key inside `options`.
        leeway=JWT_LEEWAY_SECONDS,
    )
    return cast("TokenPayload", payload)
