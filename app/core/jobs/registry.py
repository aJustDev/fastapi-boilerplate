import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

# A job returns a few words on what the run did ("3 reminders published"), or None when
# there was nothing to do: the worker writes the one line of the run with it.
JobFunc = Callable[[], Coroutine[Any, Any, str | None]]


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobFunc] = {}

    def register(self, job_name: str) -> Callable[[JobFunc], JobFunc]:
        """Decorator to register a job handler by name."""

        def decorator(func: JobFunc) -> JobFunc:
            self._jobs[job_name] = func
            logger.debug("Registered job handler %s for %s", func.__name__, job_name)
            return func

        return decorator

    def get(self, job_name: str) -> JobFunc | None:
        return self._jobs.get(job_name)

    @property
    def registered_jobs(self) -> list[str]:
        return list(self._jobs.keys())


job_registry = JobRegistry()
