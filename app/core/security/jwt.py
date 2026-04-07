import uuid
from datetime import UTC, datetime, timedelta
from typing import TypedDict

import jwt

from app.core.config import settings


class TokenPayload(TypedDict):
    sub: str
    exp: float
    iat: float
    type: str
    scopes: list[str]
    jti: str


def create_access_token(subject: str, scopes: list[str] | None = None) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "scopes": scopes or [],
        "exp": expire,
        "iat": now,
        "type": "access",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload = {
        "sub": subject,
        "scopes": [],
        "exp": expire,
        "iat": now,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token. Raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
        options={
            "require": ["exp", "iat", "sub", "jti"],
            "verify_iat": True,
            "leeway": 30,
        },
    )
