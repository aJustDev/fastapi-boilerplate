import asyncio

import pytest

from app.core.events.dispatcher import DispatchResult, EventDispatcher, HandlerResult


@pytest.fixture
def fresh_dispatcher() -> EventDispatcher:
    return EventDispatcher()


class TestHandlerResult:
    def test_success_result(self):
        r = HandlerResult(handler_name="foo", success=True)
        assert r.success is True
        assert r.error is None

    def test_failure_result(self):
        r = HandlerResult(handler_name="foo", success=False, error="boom")
        assert r.success is False
        assert r.error == "boom"


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
                HandlerResult("b", success=False, error="err"),
            ]
        )
        assert result.all_succeeded is False

    def test_errors_summary(self):
        result = DispatchResult(
            results=[
                HandlerResult("a", success=True),
                HandlerResult("b", success=False, error="err1"),
                HandlerResult("c", success=False, error="err2"),
            ]
        )
        summary = result.errors_summary
        assert "[b] err1" in summary
        assert "[c] err2" in summary
        assert "---" in summary


class TestEventDispatcher:
    async def test_register_and_dispatch(self, fresh_dispatcher: EventDispatcher):
        called_with = {}

        @fresh_dispatcher.register("test.event")
        async def handler(payload: dict) -> None:
            called_with.update(payload)

        result = await fresh_dispatcher.dispatch("test.event", {"key": "value"})

        assert result.all_succeeded is True
        assert len(result.results) == 1
        assert result.results[0].handler_name == "handler"
        assert called_with == {"key": "value"}

    async def test_multiple_handlers(self, fresh_dispatcher: EventDispatcher):
        call_order: list[str] = []

        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict) -> None:
            call_order.append("a")

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict) -> None:
            call_order.append("b")

        result = await fresh_dispatcher.dispatch("test.event", {})

        assert result.all_succeeded is True
        assert len(result.results) == 2
        assert call_order == ["a", "b"]

    async def test_no_handlers_returns_empty_result(self, fresh_dispatcher: EventDispatcher):
        result = await fresh_dispatcher.dispatch("nonexistent.event", {})
        assert result.all_succeeded is True
        assert result.results == []

    async def test_handler_failure_is_isolated(self, fresh_dispatcher: EventDispatcher):
        call_order: list[str] = []

        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict) -> None:
            call_order.append("a")
            raise ValueError("handler a failed")

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict) -> None:
            call_order.append("b")

        result = await fresh_dispatcher.dispatch("test.event", {})

        assert result.all_succeeded is False
        assert len(result.results) == 2
        assert result.results[0].success is False
        assert "ValueError" in (result.results[0].error or "")
        assert result.results[1].success is True
        assert call_order == ["a", "b"]

    async def test_handler_timeout(self, fresh_dispatcher: EventDispatcher):
        @fresh_dispatcher.register("test.slow")
        async def slow_handler(payload: dict) -> None:
            await asyncio.sleep(999)

        # Patch timeout to 0.1s for testing
        from unittest.mock import patch

        with patch("app.core.events.dispatcher.settings") as mock_settings:
            mock_settings.OUTBOX_HANDLER_TIMEOUT_SECONDS = 0.1
            result = await fresh_dispatcher.dispatch("test.slow", {})

        assert result.all_succeeded is False
        assert len(result.results) == 1
        assert result.results[0].success is False
        assert "TimeoutError" in (result.results[0].error or "")

    async def test_skips_completed_handlers(self, fresh_dispatcher: EventDispatcher):
        call_order: list[str] = []

        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict) -> None:
            call_order.append("a")

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict) -> None:
            call_order.append("b")

        result = await fresh_dispatcher.dispatch("test.event", {}, completed_handlers={"handler_a"})

        assert result.all_succeeded is True
        assert len(result.results) == 2
        # handler_a should be skipped
        assert result.results[0].handler_name == "handler_a"
        assert result.results[0].skipped is True
        assert result.results[0].success is True
        # handler_b should have run
        assert result.results[1].handler_name == "handler_b"
        assert result.results[1].skipped is False
        assert call_order == ["b"]

    async def test_skipped_handlers_not_counted_as_failures(
        self, fresh_dispatcher: EventDispatcher
    ):
        @fresh_dispatcher.register("test.event")
        async def handler_a(payload: dict) -> None:
            pass

        @fresh_dispatcher.register("test.event")
        async def handler_b(payload: dict) -> None:
            raise ValueError("fail")

        result = await fresh_dispatcher.dispatch("test.event", {}, completed_handlers={"handler_a"})

        assert result.all_succeeded is False
        assert result.results[0].skipped is True
        assert result.results[1].success is False

    def test_registered_events(self, fresh_dispatcher: EventDispatcher):
        @fresh_dispatcher.register("event.a")
        async def handler_a(payload: dict) -> None:
            pass

        @fresh_dispatcher.register("event.b")
        async def handler_b(payload: dict) -> None:
            pass

        assert sorted(fresh_dispatcher.registered_events) == ["event.a", "event.b"]
