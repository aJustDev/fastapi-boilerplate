import asyncio
import logging
import traceback
import uuid
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)

# A handler receives the payload and the id of the event. The id is what makes it
# idempotent: delivery is at least once, and the id is the same on every attempt.
HandlerFunc = Callable[[dict[str, Any], uuid.UUID], Coroutine[Any, Any, None]]


def handler_key(func: HandlerFunc) -> str:
    """Identity of a handler in `handler_state`: its module and qualified name.

    The bare function name is not enough: two contexts that react to the same event
    with a function of the same name would share one entry, and the success of one
    would hide the failure of the other.
    """
    return f"{func.__module__}.{func.__qualname__}"


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
        # event type -> {handler key -> handler}, in registration order
        self._handlers: dict[str, dict[str, HandlerFunc]] = defaultdict(dict)

    def register(self, event_type: str) -> Callable[[HandlerFunc], HandlerFunc]:
        """Decorator to register a handler for an event type."""

        def decorator(func: HandlerFunc) -> HandlerFunc:
            key = handler_key(func)
            if key in self._handlers[event_type]:
                raise ValueError(f"handler {key} is already registered for {event_type}")
            self._handlers[event_type][key] = func
            logger.info("Registered handler %s for %s", key, event_type)
            return func

        return decorator

    async def dispatch(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        event_id: uuid.UUID,
        completed_handlers: set[str] | None = None,
    ) -> DispatchResult:
        """Execute all handlers for an event type with isolation and timeout.

        Each handler runs in its own try/except so a failure in one does not
        block the others.  Handlers whose keys (`handler_key`) appear in
        *completed_handlers* are skipped (marked as ``skipped=True`` in the result).

        Zero registered handlers is an error, not a no-op: the result carries
        ``no_handlers=True`` so the caller retries instead of acknowledging.

        Returns a DispatchResult with per-handler outcomes.
        """
        handlers = self._handlers.get(event_type, {})
        if not handlers:
            logger.critical("No handlers registered for event_type=%s", event_type)
            return DispatchResult(no_handlers=True)

        completed = completed_handlers or set()
        result = DispatchResult()
        for key, handler in handlers.items():
            if key in completed:
                result.results.append(HandlerResult(key, success=True, skipped=True))
                continue

            try:
                await asyncio.wait_for(
                    handler(payload, event_id),
                    timeout=settings.OUTBOX_HANDLER_TIMEOUT_SECONDS,
                )
                result.results.append(HandlerResult(key, success=True))
            except Exception:
                tb = traceback.format_exc()
                logger.exception("Handler %s failed for event_type=%s", key, event_type)
                result.results.append(HandlerResult(key, success=False, error=tb))

        return result

    @property
    def registered_events(self) -> list[str]:
        return list(self._handlers.keys())


# Module-level singleton
dispatcher = EventDispatcher()
