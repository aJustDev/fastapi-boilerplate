from app.core.db import async_session_factory
from app.core.jobs.registry import job_registry
from app.workshops.repos.workshop import WorkshopRepo


@job_registry.register("workshops_finish")
async def workshops_finish() -> str | None:
    """Published workshops whose end has passed become finished.

    The one transition nobody asks for: time causes it, so a job applies it.
    """
    async with async_session_factory() as session:
        finished = await WorkshopRepo(session).finish_ended()
        await session.commit()
    return f"{finished} workshop{'s' * (finished != 1)} finished" if finished else None
