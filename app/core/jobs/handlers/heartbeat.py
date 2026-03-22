import logging
import os
import socket

from app.core.jobs.registry import job_registry

logger = logging.getLogger(__name__)


@job_registry.register("heartbeat_check")
async def heartbeat_check() -> None:
    """Example job that verifies which worker instance runs it."""
    logger.debug(
        "heartbeat from %s (PID=%d)",
        socket.gethostname(),
        os.getpid(),
    )
