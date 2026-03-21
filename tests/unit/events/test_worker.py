import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.core.events.dispatcher import DispatchResult, HandlerResult
from app.core.events.worker import OutboxWorker
from app.models.events.outbox import OutboxEventORM


def _make_event(
    *,
    status: str = "PENDING",
    retry_count: int = 0,
    max_retries: int = 5,
    handler_state: dict | None = None,
) -> OutboxEventORM:
    event = OutboxEventORM(
        id=uuid.uuid4(),
        event_type="test.event",
        payload={"key": "value"},
        status=status,
        retry_count=retry_count,
        max_retries=max_retries,
        scheduled_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        handler_state=handler_state or {},
    )
    return event


class TestHandleEvent:
    async def test_marks_processed_on_success(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event()

        success_result = DispatchResult(results=[HandlerResult("handler_a", success=True)])

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=success_result,
        ):
            await worker._handle_event(session, event)

        assert event.status == "PROCESSED"
        assert event.processed_at is not None
        session.flush.assert_called_once()

    async def test_increments_retry_on_failure(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event(retry_count=0, max_retries=5)

        failure_result = DispatchResult(
            results=[HandlerResult("handler_a", success=False, error="boom")]
        )

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=failure_result,
        ):
            await worker._handle_event(session, event)

        assert event.status == "PENDING"
        assert event.retry_count == 1
        assert event.last_error is not None
        assert "boom" in event.last_error
        # scheduled_at should be in the future (backoff)
        assert event.scheduled_at > datetime.now(UTC) - timedelta(seconds=1)

    async def test_marks_failed_at_max_retries(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event(retry_count=4, max_retries=5)

        failure_result = DispatchResult(
            results=[HandlerResult("handler_a", success=False, error="final failure")]
        )

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=failure_result,
        ):
            await worker._handle_event(session, event)

        assert event.status == "FAILED"
        assert event.retry_count == 5
        assert "final failure" in event.last_error

    async def test_backoff_increases_with_retry_count(self):
        worker = OutboxWorker()
        session = AsyncMock()

        failure_result = DispatchResult(results=[HandlerResult("h", success=False, error="err")])

        # Test retry 1 vs retry 3 — retry 3 should have a larger delay
        event_low = _make_event(retry_count=0, max_retries=10)
        event_high = _make_event(retry_count=2, max_retries=10)

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=failure_result,
        ):
            now = datetime.now(UTC)
            await worker._handle_event(session, event_low)
            await worker._handle_event(session, event_high)

        # retry_count 1 → ~2s backoff, retry_count 3 → ~8s backoff
        delay_low = (event_low.scheduled_at - now).total_seconds()
        delay_high = (event_high.scheduled_at - now).total_seconds()
        assert delay_high > delay_low

    async def test_last_error_stores_errors_summary(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event(retry_count=0, max_retries=5)

        failure_result = DispatchResult(
            results=[
                HandlerResult("handler_a", success=True),
                HandlerResult("handler_b", success=False, error="traceback B"),
                HandlerResult("handler_c", success=False, error="traceback C"),
            ]
        )

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=failure_result,
        ):
            await worker._handle_event(session, event)

        assert "[handler_b]" in event.last_error
        assert "[handler_c]" in event.last_error
        assert "traceback B" in event.last_error
        assert "traceback C" in event.last_error


class TestHandlerState:
    async def test_handler_state_records_success(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event()

        success_result = DispatchResult(results=[HandlerResult("handler_a", success=True)])

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=success_result,
        ):
            await worker._handle_event(session, event)

        assert "handler_a" in event.handler_state
        assert event.handler_state["handler_a"]["status"] == "ok"

    async def test_handler_state_records_failure(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event()

        failure_result = DispatchResult(
            results=[HandlerResult("handler_a", success=False, error="boom")]
        )

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=failure_result,
        ):
            await worker._handle_event(session, event)

        assert event.handler_state["handler_a"]["status"] == "failed"
        assert "boom" in event.handler_state["handler_a"]["error"]

    async def test_completed_handlers_passed_to_dispatcher(self):
        worker = OutboxWorker()
        session = AsyncMock()
        event = _make_event(
            handler_state={"handler_a": {"status": "ok", "at": "2026-01-01T00:00:00"}},
        )

        success_result = DispatchResult(
            results=[
                HandlerResult("handler_a", success=True, skipped=True),
                HandlerResult("handler_b", success=True),
            ]
        )

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=success_result,
        ) as mock_dispatch:
            await worker._handle_event(session, event)

        # Verify completed_handlers was passed with handler_a
        _, kwargs = mock_dispatch.call_args
        assert "handler_a" in kwargs["completed_handlers"]

    async def test_skipped_handlers_not_overwritten_in_state(self):
        worker = OutboxWorker()
        session = AsyncMock()
        original_state = {"handler_a": {"status": "ok", "at": "2026-01-01T00:00:00"}}
        event = _make_event(handler_state=original_state)

        result = DispatchResult(
            results=[
                HandlerResult("handler_a", success=True, skipped=True),
                HandlerResult("handler_b", success=True),
            ]
        )

        with patch(
            "app.core.events.worker.dispatcher.dispatch",
            return_value=result,
        ):
            await worker._handle_event(session, event)

        # handler_a should keep its original timestamp
        assert event.handler_state["handler_a"]["at"] == "2026-01-01T00:00:00"
        # handler_b should be newly recorded
        assert event.handler_state["handler_b"]["status"] == "ok"
        assert event.status == "PROCESSED"
