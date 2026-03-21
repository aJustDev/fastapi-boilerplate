from pydantic import BaseModel


class RegisterRequest(BaseModel):
    email: str
    username: str
    password: str
    full_name: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
