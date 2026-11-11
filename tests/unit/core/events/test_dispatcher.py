import asyncio
import logging
import uuid

import pytest

from app.core.events.dispatcher import (
    DispatchResult,
    EventDispatcher,
    ExpectedFailure,
    HandlerResult,
    HandlerTimeoutError,
    handler_key,
)

EVENT_ID = uuid.uuid4()


@pytest.fixture
def fresh_dispatcher() -> EventDispatcher:
    return EventDispatcher()


class TestHandlerResult:
    def test_success_result(self):
        r = HandlerResult(handler_name="foo", success=True)
        assert r.success is True
        assert r.error is None

    def test_a_bug_is_stored_as_its_traceback(self):
        r = HandlerResult(handler_name="foo", success=False, exception=ValueError("boom"))
        assert r.expected is False
        assert r.error == "ValueError: boom\n"

    def test_an_expected_failure_is_stored_as_its_line(self):
        r = HandlerResult(
            handler_name="foo",
            success=False,
            reason="foo failed (ExpectedFailure: no)",
            exception=ExpectedFailure("no"),
        )
        assert r.expected is True
        assert r.error == "foo failed (ExpectedFailure: no)"


class TestDispatchResult:
    def test_all_succeeded_when_empty(self):
        assert DispatchResult().all_succeeded is True

    def test_all_succeeded_true(self):
        result = DispatchResult(
            results=[
                HandlerResult("a", success=True),
                HandlerResult("b", success=True),
            ]
        )
        assert result.all_succeeded is True

    def test_all_succeeded_false(self):
        result = DispatchResult(
            results=[
                HandlerResult("a", success=True),
                HandlerResult("b", success=False, exception=ValueError("err")),
            ]
        )
        assert result.all_succeeded is False

    def test_errors_summary(self):
        result = DispatchResult(
            results=[
                HandlerResult("a", success=True),
                HandlerResult("b", success=False, exception=ValueError("err1")),
                HandlerResult("c", success=False, exception=ValueError("err2")),
            ]
        )
        summary = result.errors_summary
        assert "[b] ValueError: err1" in summary
        assert "[c] ValueError: err2" in summary
        assert "---" in summary


class TestEventDispatcher:
    async def test_register_and_dispatch(self, fresh_dispatcher: EventDispatcher):
        called_with = {}

        @fresh_dispatcher.register("test.event")
        async def handler(payload: dict, event_id: uuid.UUID) -> None:
            called_with.update(payload)

        result = await fresh_dispatcher.dispatch("test.event", {"key": "value"}, event_id=EVENT_ID)

        assert result.all_succeeded is True
        assert len(result.results) == 1
        assert result.results[0].handler_name == handler_key(handler)
        assert called_with == {"key": "value"}

    async def test_multiple_handlers(self, fresh_dispatcher: EventDispatcher):
        call_order: list[str] = []

        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict, event_id: uuid.UUID) -> None:
            call_order.append("a")

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict, event_id: uuid.UUID) -> None:
            call_order.append("b")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        assert result.all_succeeded is True
        assert len(result.results) == 2
        assert call_order == ["a", "b"]

    async def test_no_handlers_is_not_a_success(self, fresh_dispatcher: EventDispatcher):
        # An event nobody handles must be retried, not acknowledged as processed.
        result = await fresh_dispatcher.dispatch("nonexistent.event", {}, event_id=EVENT_ID)
        assert result.no_handlers is True
        assert result.all_succeeded is False
        assert result.results == []
        assert "no handlers" in result.errors_summary

    async def test_handler_failure_is_isolated(self, fresh_dispatcher: EventDispatcher):
        call_order: list[str] = []

        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict, event_id: uuid.UUID) -> None:
            call_order.append("a")
            raise ValueError("handler a failed")

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict, event_id: uuid.UUID) -> None:
            call_order.append("b")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        assert result.all_succeeded is False
        assert len(result.results) == 2
        assert result.results[0].success is False
        assert "ValueError" in (result.results[0].error or "")
        assert result.results[1].success is True
        assert call_order == ["a", "b"]

    async def test_handler_timeout(self, fresh_dispatcher: EventDispatcher):
        @fresh_dispatcher.register("test.slow")
        async def slow_handler(payload: dict, event_id: uuid.UUID) -> None:
            await asyncio.sleep(999)

        # Patch timeout to 0.1s for testing
        from unittest.mock import patch

        with patch("app.core.events.dispatcher.settings") as mock_settings:
            mock_settings.OUTBOX_HANDLER_TIMEOUT_SECONDS = 0.1
            result = await fresh_dispatcher.dispatch("test.slow", {}, event_id=EVENT_ID)

        assert result.all_succeeded is False
        assert len(result.results) == 1
        assert result.results[0].success is False
        # Running past the deadline is a failure with a name: one line, no traceback to
        # store or show.
        [failure] = result.results
        assert isinstance(failure.exception, HandlerTimeoutError)
        assert failure.expected is True
        line = "test_dispatcher.slow_handler failed (HandlerTimeoutError: still running after 0.1s)"
        assert result.failures == line
        assert failure.error == line
        assert result.bug is None

    async def test_skips_completed_handlers(self, fresh_dispatcher: EventDispatcher):
        call_order: list[str] = []

        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict, event_id: uuid.UUID) -> None:
            call_order.append("a")

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict, event_id: uuid.UUID) -> None:
            call_order.append("b")

        result = await fresh_dispatcher.dispatch(
            "test.event", {}, event_id=EVENT_ID, completed_handlers={handler_key(handler_a)}
        )

        assert result.all_succeeded is True
        assert len(result.results) == 2
        # handler_a should be skipped
        assert result.results[0].handler_name == handler_key(handler_a)
        assert result.results[0].skipped is True
        assert result.results[0].success is True
        # handler_b should have run
        assert result.results[1].handler_name == handler_key(handler_b)
        assert result.results[1].skipped is False
        assert call_order == ["b"]

    async def test_skipped_handlers_not_counted_as_failures(
        self, fresh_dispatcher: EventDispatcher
    ):
        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict, event_id: uuid.UUID) -> None:
            pass

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict, event_id: uuid.UUID) -> None:
            raise ValueError("fail")

        result = await fresh_dispatcher.dispatch(
            "test.event", {}, event_id=EVENT_ID, completed_handlers={handler_key(handler_a)}
        )

        assert result.all_succeeded is False
        assert result.results[0].skipped is True
        assert result.results[1].success is False

    def test_registered_events(self, fresh_dispatcher: EventDispatcher):
        @fresh_dispatcher.register("event.a")
        async def handler_a(payload: dict, event_id: uuid.UUID) -> None:
            pass

        @fresh_dispatcher.register("event.b")
        async def handler_b(payload: dict, event_id: uuid.UUID) -> None:
            pass

        assert sorted(fresh_dispatcher.registered_events) == ["event.a", "event.b"]


class TestWhatAFailureLogs:
    """The worker writes the attempt; the dispatcher only reports what failed."""

    async def test_a_failing_handler_is_reported_not_logged(self, fresh_dispatcher, caplog):
        @fresh_dispatcher.register("test.event")
        async def notify(payload: dict, event_id: uuid.UUID) -> None:
            raise ValueError("bad input")

        with caplog.at_level(logging.DEBUG, logger="app.core.events.dispatcher"):
            result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        assert caplog.records == []
        assert result.failures == "test_dispatcher.notify failed (ValueError: bad input)"
        assert "Traceback" in result.errors_summary, "the stored error keeps the traceback"

    def test_without_handlers_the_failure_says_so(self):
        assert DispatchResult(no_handlers=True).failures == (
            "no handlers registered for this event_type"
        )


class TestExpectedFailures:
    """A failure the handler can name has no traceback worth showing; a bug does."""

    async def test_an_expected_failure_is_one_line_everywhere(self, fresh_dispatcher):
        @fresh_dispatcher.register("test.event")
        async def deliver(payload: dict, event_id: uuid.UUID) -> None:
            raise ExpectedFailure("receiver answered 404")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        [failure] = result.results
        assert failure.expected is True
        line = "test_dispatcher.deliver failed (ExpectedFailure: receiver answered 404)"
        assert result.failures == line
        assert failure.error == line, "the stored error is the line, not a traceback"
        assert result.bug is None

    async def test_a_bug_keeps_its_traceback(self, fresh_dispatcher):
        @fresh_dispatcher.register("test.event")
        async def deliver(payload: dict, event_id: uuid.UUID) -> None:
            raise KeyError("workshop_id")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        [failure] = result.results
        assert isinstance(result.bug, KeyError), "the exception itself, for the log to format"
        assert result.bug.__notes__ == [f"handler: {handler_key(deliver)}"]
        assert "Traceback (most recent call last)" in failure.error

    async def test_a_timeout_of_the_handler_itself_is_not_the_deadline(self, fresh_dispatcher):
        # asyncpg's command_timeout, an asyncio.timeout() or a socket raise TimeoutError too:
        # it failed at once, for a reason of its own that only its traceback shows.
        @fresh_dispatcher.register("test.event")
        async def charge(payload: dict, event_id: uuid.UUID) -> None:
            raise TimeoutError("billing did not answer")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        [failure] = result.results
        assert failure.expected is False
        assert result.failures == (
            "test_dispatcher.charge failed (TimeoutError: billing did not answer)"
        )
        assert isinstance(result.bug, TimeoutError)
        assert "Traceback (most recent call last)" in failure.error

    async def test_several_bugs_travel_as_a_group_each_with_its_handler(self, fresh_dispatcher):
        @fresh_dispatcher.register("test.event")
        async def first(payload: dict, event_id: uuid.UUID) -> None:
            raise KeyError("workshop_id")

        @fresh_dispatcher.register("test.event")
        async def second(payload: dict, event_id: uuid.UUID) -> None:
            raise ValueError("bad payload")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        assert isinstance(result.bug, ExceptionGroup)
        assert [(type(e), e.__notes__) for e in result.bug.exceptions] == [
            (KeyError, [f"handler: {handler_key(first)}"]),
            (ValueError, [f"handler: {handler_key(second)}"]),
        ]

    async def test_an_expected_failure_next_to_a_bug_leaves_the_bug_alone(self, fresh_dispatcher):
        @fresh_dispatcher.register("test.event")
        async def deliver(payload: dict, event_id: uuid.UUID) -> None:
            raise ExpectedFailure("receiver answered 503")

        @fresh_dispatcher.register("test.event")
        async def record(payload: dict, event_id: uuid.UUID) -> None:
            raise KeyError("workshop_id")

        result = await fresh_dispatcher.dispatch("test.event", {}, event_id=EVENT_ID)

        assert isinstance(result.bug, KeyError)
        assert result.failures == (
            "test_dispatcher.deliver failed (ExpectedFailure: receiver answered 503); "
            "test_dispatcher.record failed (KeyError: 'workshop_id')"
        )
