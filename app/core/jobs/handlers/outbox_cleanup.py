import logging

from app.core.events.cleanup import cleanup_processed_events
from app.core.jobs.registry import job_registry

logger = logging.getLogger(__name__)


@job_registry.register("outbox_cleanup")
async def outbox_cleanup() -> None:
    """Delete PROCESSED outbox events older than OUTBOX_CLEANUP_DAYS.

    Every event leaves a row; without this the table only grows. FAILED events are kept:
    they wait for `python -m app.cli outbox replay` or for someone to decide they are lost.
    """
    await cleanup_processed_events()
