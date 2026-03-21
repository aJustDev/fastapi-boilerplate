from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.events.bus import EventBus


async def get_event_bus(
    session: AsyncSession = Depends(get_session),
) -> EventBus:
    return EventBus(session)
