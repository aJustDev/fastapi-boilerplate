from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.repo import BaseRepo


def get_repo[T: BaseRepo](repo_class: type[T]) -> Callable[..., Awaitable[T]]:
    """Factory that returns a FastAPI dependency for any repository class."""

    async def _get(session: Annotated[AsyncSession, Depends(get_session)]) -> T:
        return repo_class(session)

    return _get
