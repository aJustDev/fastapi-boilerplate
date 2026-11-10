from dataclasses import dataclass
from datetime import timedelta

from app.core.events.bus import EventBus
from app.workshops.repos.enrollment import EnrollmentRepo

REMINDER_WINDOW = timedelta(hours=24)
# Per run. What is left over is picked up by the next one, a few minutes later.
BATCH_SIZE = 500


@dataclass(slots=True)
class SendRemindersUseCase:
    enrollment_repo: EnrollmentRepo
    event_bus: EventBus

    async def execute(self) -> int:
        """Publish one reminder per confirmed attendee of a workshop about to start.

        Marking an enrollment as reminded and publishing its event share a transaction:
        either both are stored or neither, so nobody is reminded twice or skipped.
        """
        due = await self.enrollment_repo.claim_due_reminders(
            within=REMINDER_WINDOW, limit=BATCH_SIZE
        )
        return await self.event_bus.publish_many(
            "enrollment.reminder",
            [
                (
                    row.enrollment_id,
                    {
                        "enrollment_id": row.enrollment_id,
                        "workshop_id": row.workshop_id,
                        "attendee_id": row.attendee_id,
                        "title": row.title,
                        "starts_at": row.starts_at.isoformat(),
                    },
                )
                for row in due
            ],
        )
