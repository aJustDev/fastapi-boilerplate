from collections.abc import Callable
from typing import TypeVar

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.repos.base import BaseRepo

T = TypeVar("T", bound=BaseRepo)


def get_repo(repo_class: type[T]) -> Callable[..., T]:
    """Factory that returns a FastAPI dependency for any repository class."""

    async def _get(session: AsyncSession = Depends(get_session)) -> T:
        return repo_class(session)

    return _get
