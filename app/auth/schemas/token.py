from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, Field, StringConstraints

from app.core.schema import ShortText, reject_nul

# Longest login identifier (an email address) and password the API accepts. Login checks
# them too: anything longer cannot belong to an account.
MAX_IDENTIFIER_LENGTH = 320
MAX_PASSWORD_LENGTH = 128

# No "@" and no spaces: a username can never look like someone else's email, which is the
# other identifier login accepts.
Username = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9._-]{3,50}$")]
Password = Annotated[
    str,
    StringConstraints(min_length=8, max_length=MAX_PASSWORD_LENGTH),
    AfterValidator(reject_nul),
]
# A JWT of this API is a few hundred characters.
Token = Annotated[str, StringConstraints(min_length=1, max_length=2048)]


class RegisterRequest(BaseModel):
    email: EmailStr = Field(
        description="Unique, compared without case", examples=["ada@example.com"]
    )
    username: Username = Field(
        description="Unique, compared without case: 3 to 50 letters, digits, `.`, `_` or `-`",
        examples=["ada"],
    )
    password: Password = Field(
        description="8 to 128 characters", examples=["correct-horse-battery"]
    )
    full_name: ShortText | None = Field(
        default=None, description="Display name", examples=["Ada Lovelace"]
    )


class RefreshRequest(BaseModel):
    refresh_token: Token = Field(description="The refresh token of the last login or refresh")


class LogoutRequest(BaseModel):
    """Optional body of /logout: the refresh token to revoke along with the access token."""

    refresh_token: Token | None = Field(
        default=None,
        description="Revoked too when sent; otherwise it stays valid until it expires",
    )


class TokenResponse(BaseModel):
    access_token: str = Field(description="Bearer token for the Authorization header")
    refresh_token: str = Field(description="Single use: exchange it at /auth/refresh")
    token_type: str = "bearer"  # noqa: S105 -- OAuth2 token type, not a secret
