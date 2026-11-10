from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.events.bus import EventBus


async def get_event_bus(
    # Same scope as in app/deps/repository.py: the scope is part of the dependency cache
    # key, and a different one here would give the bus a second session.
    session: Annotated[AsyncSession, Depends(get_session, scope="function")],
) -> EventBus:
    return EventBus(session)
