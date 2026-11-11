from app.core.db import async_session_factory
from app.core.events.bus import EventBus
from app.core.jobs.registry import job_registry
from app.workshops.repos.enrollment import EnrollmentRepo
from app.workshops.use_cases.send_reminders import SendRemindersUseCase


@job_registry.register("workshop_reminders")
async def workshop_reminders() -> str | None:
    """Remind the confirmed attendees of workshops that start within a day.

    The job only decides who is due and publishes one event each; the delivery, with its
    retries, is the outbox worker's. Running it twice, or on two workers at once, reminds
    nobody twice: an enrollment is marked in the transaction that publishes its event.
    """
    async with async_session_factory() as session:
        sent = await SendRemindersUseCase(EnrollmentRepo(session), EventBus(session)).execute()
        await session.commit()
    return f"{sent} reminder{'s' * (sent != 1)} published" if sent else None
