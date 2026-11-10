from typing import Annotated

from pydantic import AfterValidator, BaseModel, EmailStr, StringConstraints

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
    email: EmailStr
    username: Username
    password: Password
    full_name: ShortText | None = None


class RefreshRequest(BaseModel):
    refresh_token: Token


class LogoutRequest(BaseModel):
    """Optional body of /logout: the refresh token to revoke along with the access token."""

    refresh_token: Token | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 -- OAuth2 token type, not a secret
