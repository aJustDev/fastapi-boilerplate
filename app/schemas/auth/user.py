from datetime import datetime

from pydantic import EmailStr

from app.schemas.base import BaseSchema


class UserCreate(BaseSchema):
    email: EmailStr
    username: str
    password: str
    full_name: str | None = None


class UserRead(BaseSchema):
    id: int
    email: str
    username: str
    full_name: str | None
    is_active: bool
    created_at: datetime
    roles: list["RoleRead"] = []


class RoleRead(BaseSchema):
    id: int
    name: str
    description: str | None


class PermissionRead(BaseSchema):
    id: int
    name: str
    description: str | None
