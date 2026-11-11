import asyncio
import logging
import traceback
import uuid
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings
from app.core.logging.errors import one_line

logger = logging.getLogger(__name__)

# A handler receives the payload and the id of the event. The id is what makes it
# idempotent: delivery is at least once, and the id is the same on every attempt.
HandlerFunc = Callable[[dict[str, Any], uuid.UUID], Coroutine[Any, Any, None]]


class ExpectedFailure(Exception):  # noqa: N818 -- it names what it is, not an error class
    """A failure the handler can name: a receiver that said no, a service that did not answer.

    Retried like any failure, and logged in one line on every attempt: a traceback would
    only show where the handler raised it. Any other exception is a bug, and its traceback
    goes with the first and the last attempt.
    """


class HandlerTimeoutError(ExpectedFailure):
    """The handler was still running when its time was up (OUTBOX_HANDLER_TIMEOUT_SECONDS)."""

    def __init__(self, seconds: float) -> None:
        super().__init__(f"still running after {seconds:g}s")


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
    skipped: bool = False
    reason: str | None = None  # `notifications.notify_confirmed failed (ConnectTimeout)`
    exception: Exception | None = None  # what the handler raised

    @property
    def expected(self) -> bool:
        """A failure the handler could name: its line says it all."""
        return isinstance(self.exception, ExpectedFailure)

    @property
    def error(self) -> str | None:
        """What is stored with the event: the line of an expected failure, a bug's traceback."""
        if self.exception is None:
            return None
        if self.expected:
            return self.reason or one_line(self.exception)
        return "".join(traceback.format_exception(self.exception))


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

    @property
    def bug(self) -> Exception | None:
        """What a log line brings as `exc_info`: the exception of the handler that failed
        unexpectedly, a group if several did, None if none did."""
        bugs = [r.exception for r in self.results if r.exception is not None and not r.expected]
        if len(bugs) > 1:
            return ExceptionGroup(f"{len(bugs)} handlers failed", bugs)
        return bugs[0] if bugs else None

    @property
    def failures(self) -> str:
        """What failed, in one line: `notifications.notify_confirmed failed (ConnectTimeout)`."""
        if self.no_handlers:
            return "no handlers registered for this event_type"
        return "; ".join(
            r.reason or f"{r.handler_name} failed" for r in self.results if not r.success
        )


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
            logger.debug("Registered handler %s for %s", key, event_type)
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
            # The worker says it on every attempt and gives up loudly (CRITICAL).
            logger.debug("No handlers registered for %s", event_type)
            return DispatchResult(no_handlers=True)

        completed = completed_handlers or set()
        result = DispatchResult()
        for key, handler in handlers.items():
            if key in completed:
                result.results.append(HandlerResult(key, success=True, skipped=True))
                continue

            deadline = asyncio.timeout(settings.OUTBOX_HANDLER_TIMEOUT_SECONDS)
            try:
                async with deadline:
                    await handler(payload, event_id)
                result.results.append(HandlerResult(key, success=True))
            # The worker logs the attempt, and the exception with it when it is a bug.
            except Exception as exc:  # noqa: BLE001
                failure: Exception = exc
                # Only the deadline above: a TimeoutError the handler raised by itself (a
                # query, a socket) is a failure like any other, with its traceback.
                if isinstance(exc, TimeoutError) and deadline.expired():
                    failure = HandlerTimeoutError(settings.OUTBOX_HANDLER_TIMEOUT_SECONDS)
                elif not isinstance(exc, ExpectedFailure):
                    # Where several handlers fail, which traceback is whose.
                    exc.add_note(f"handler: {key}")
                # The module and the function: enough to find it, short enough for a line.
                label = f"{handler.__module__.rsplit('.', 1)[-1]}.{handler.__name__}"
                result.results.append(
                    HandlerResult(
                        key,
                        success=False,
                        reason=f"{label} failed ({one_line(failure)})",
                        exception=failure,
                    )
                )

        return result

    @property
    def registered_events(self) -> list[str]:
        return list(self._handlers.keys())


# Module-level singleton
dispatcher = EventDispatcher()
