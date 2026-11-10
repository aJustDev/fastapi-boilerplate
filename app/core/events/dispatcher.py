import asyncio
import logging
import traceback
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

HandlerFunc = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


@dataclass
class HandlerResult:
    handler_name: str
    success: bool
    error: str | None = None
    skipped: bool = False


@dataclass
class DispatchResult:
    results: list[HandlerResult] = field(default_factory=list)
    no_handlers: bool = False

    @property
    def all_succeeded(self) -> bool:
        # `all([])` is True: without this guard an event with no registered handler
        # (typo in the event_type, handler module never imported) would be marked
        # PROCESSED and its side effects silently lost.
        if self.no_handlers:
            return False
        return all(r.success for r in self.results)

    @property
    def errors_summary(self) -> str:
        if self.no_handlers:
            return "no handlers registered for this event_type"
        failed = [r for r in self.results if not r.success]
        return "\n---\n".join(f"[{r.handler_name}] {r.error}" for r in failed)


class EventDispatcher:
    def __init__(self) -> None:
        self._handlers: dict[str, list[HandlerFunc]] = defaultdict(list)

    def register(self, event_type: str) -> Callable[[HandlerFunc], HandlerFunc]:
        """Decorator to register a handler for an event type."""

        def decorator(func: HandlerFunc) -> HandlerFunc:
            self._handlers[event_type].append(func)
            logger.info("Registered handler %s for %s", func.__name__, event_type)
            return func

        return decorator

    async def dispatch(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        completed_handlers: set[str] | None = None,
    ) -> DispatchResult:
        """Execute all handlers for an event type with isolation and timeout.

        Each handler runs in its own try/except so a failure in one does not
        block the others.  Handlers whose names appear in *completed_handlers*
        are skipped (marked as ``skipped=True`` in the result).

        Zero registered handlers is an error, not a no-op: the result carries
        ``no_handlers=True`` so the caller retries instead of acknowledging.

        Returns a DispatchResult with per-handler outcomes.
        """
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.critical("No handlers registered for event_type=%s", event_type)
            return DispatchResult(no_handlers=True)

        completed = completed_handlers or set()
        result = DispatchResult()
        for handler in handlers:
            if handler.__name__ in completed:
                result.results.append(
                    HandlerResult(handler.__name__, success=True, skipped=True),
                )
                continue

            try:
                await asyncio.wait_for(
                    handler(payload),
                    timeout=settings.OUTBOX_HANDLER_TIMEOUT_SECONDS,
                )
                result.results.append(
                    HandlerResult(handler.__name__, success=True),
                )
            except Exception:
                tb = traceback.format_exc()
                logger.exception(
                    "Handler %s failed for event_type=%s",
                    handler.__name__,
                    event_type,
                )
                result.results.append(
                    HandlerResult(handler.__name__, success=False, error=tb),
                )

        return result

    @property
    def registered_events(self) -> list[str]:
        return list(self._handlers.keys())


# Module-level singleton
dispatcher = EventDispatcher()
