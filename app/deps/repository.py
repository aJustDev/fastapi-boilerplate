from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.repo import BaseRepo


def get_repo[T: BaseRepo](repo_class: type[T]) -> Callable[..., Awaitable[T]]:
    """Factory that returns a FastAPI dependency for any repository class."""

    # scope="function": get_session commits when the endpoint returns, before the response
    # is sent. With the default scope of a `yield` dependency the commit would run after
    # the client already has its 2xx, and a failed commit would go unreported.
    async def _get(session: Annotated[AsyncSession, Depends(get_session, scope="function")]) -> T:
        return repo_class(session)

    return _get
