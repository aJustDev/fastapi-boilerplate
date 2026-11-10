from datetime import datetime

from pydantic import Field

from app.core.schema import BaseSchema


class RoleRead(BaseSchema):
    id: int
    name: str = Field(examples=["user"])
    description: str | None


class UserRead(BaseSchema):
    id: int
    email: str
    username: str
    full_name: str | None
    is_active: bool = Field(description="An inactive account cannot log in or use its tokens")
    created_at: datetime
    roles: list[RoleRead] = Field(
        default=[], description="Roles; their permissions guard the routes"
    )
