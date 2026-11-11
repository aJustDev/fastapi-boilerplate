import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from app.core.events.dispatcher import DispatchResult, HandlerResult
from app.core.events.models import OutboxEventORM
from app.core.events.worker import OutboxWorker
from app.core.logging.context import request_id_var


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


class TestRetryBudget:
    async def test_default_settings_ride_out_an_hour_of_failures(self):
        # What a handler calls (a mail provider, a webhook receiver) restarts and has
        # outages. An event must still be PENDING when it comes back, not FAILED and
        # waiting for someone to replay it by hand.
        from app.core.config import Settings

        worker, session = OutboxWorker(), AsyncMock()
        event = _make_event(max_retries=Settings(ENVIRONMENT="local").OUTBOX_MAX_RETRIES)
        failure = DispatchResult(results=[HandlerResult("handler_a", success=False, error="x")])
        waited = timedelta()

        with patch("app.core.events.worker.dispatcher.dispatch", return_value=failure):
            while event.status == "PENDING":
                before = datetime.now(UTC)
                await worker._handle_event(session, event)
                if event.status == "PENDING":
                    waited += event.scheduled_at - before

        assert event.status == "FAILED"
        assert waited >= timedelta(hours=1)


class TestWorkerMetrics:
    @staticmethod
    def _count(counter, event_type: str) -> float:
        return counter.labels(event_type=event_type)._value.get()

    async def test_a_processed_event_is_counted(self):
        from app.core.metrics.instruments import outbox_events_processed_total

        worker, session, event = OutboxWorker(), AsyncMock(), _make_event()
        before = self._count(outbox_events_processed_total, event.event_type)
        ok = DispatchResult(results=[HandlerResult("handler_a", success=True)])

        with patch("app.core.events.worker.dispatcher.dispatch", return_value=ok):
            await worker._handle_event(session, event)

        assert self._count(outbox_events_processed_total, event.event_type) == before + 1

    async def test_an_event_out_of_retries_is_counted_as_failed(self):
        from app.core.metrics.instruments import outbox_events_failed_total

        worker, session = OutboxWorker(), AsyncMock()
        event = _make_event(retry_count=4, max_retries=5)
        before = self._count(outbox_events_failed_total, event.event_type)
        failure = DispatchResult(results=[HandlerResult("handler_a", success=False, error="x")])

        with patch("app.core.events.worker.dispatcher.dispatch", return_value=failure):
            await worker._handle_event(session, event)

        assert event.status == "FAILED"
        assert self._count(outbox_events_failed_total, event.event_type) == before + 1


class TestCorrelation:
    async def test_handlers_run_under_the_request_id_of_the_publisher(self):
        from app.core.events.dispatcher import EventDispatcher
        from app.core.logging.context import get_request_id

        seen: list[str] = []
        dispatcher = EventDispatcher()

        @dispatcher.register("test.event")
        async def record(payload: dict, event_id: uuid.UUID) -> None:
            seen.append(get_request_id())

        event = _make_event()
        event.correlation_id = "trace-42"

        with patch("app.core.events.worker.dispatcher", dispatcher):
            await OutboxWorker()._handle_event(AsyncMock(), event)

        assert seen == ["trace-42"]
        assert get_request_id() == ""  # and it does not leak into the worker loop


class TestStop:
    async def test_a_worker_that_never_started_reports_nothing(self, caplog):
        # OUTBOX_WORKER_ENABLED=false: the lifespan still calls stop().
        with caplog.at_level("INFO", logger="app.core.events.worker"):
            await OutboxWorker().stop()
        assert "stopped" not in caplog.text


class TestWhatAnAttemptLogs:
    """One line per attempt, without a traceback; the traceback stays with the event."""

    _FAILED = DispatchResult(
        results=[
            HandlerResult(
                "app.x.notifications.notify",
                success=False,
                error="Traceback ...",
                reason="notifications.notify failed (ConnectTimeout)",
            )
        ]
    )

    async def _handle(self, event, caplog):
        with (
            patch("app.core.events.worker.dispatcher.dispatch", return_value=self._FAILED),
            caplog.at_level("INFO", logger="app.core.events.worker"),
        ):
            await OutboxWorker()._handle_event(AsyncMock(), event)
        return [r for r in caplog.records if r.name == "app.core.events.worker"]

    async def test_an_attempt_between_the_first_and_the_last_is_one_line(self, caplog):
        event = _make_event(retry_count=3, max_retries=12)

        [record] = await self._handle(event, caplog)

        assert record.levelname == "WARNING"
        assert record.exc_info is None
        message = record.getMessage()
        assert message.startswith(f"Retry 4/12 of test.event {event.id} in ")
        assert message.endswith("s: notifications.notify failed (ConnectTimeout)")

    async def test_the_first_failure_brings_its_traceback(self, caplog):
        # To debug a handler without waiting for its last attempt, an hour later.
        [record] = await self._handle(_make_event(retry_count=0, max_retries=12), caplog)

        first_line, traceback = record.getMessage().split("\n", 1)
        assert first_line.startswith("Retry 1/12 of test.event ")
        assert traceback == "[app.x.notifications.notify] Traceback ..."

    async def test_the_last_attempt_brings_its_traceback(self, caplog):
        event = _make_event(retry_count=11, max_retries=12)

        [record] = await self._handle(event, caplog)

        assert record.levelname == "CRITICAL"
        first_line, traceback = record.getMessage().split("\n", 1)
        assert first_line.startswith(
            f"Gave up on test.event {event.id} after 12 attempts: "
            "notifications.notify failed (ConnectTimeout); "
        )
        assert traceback == "[app.x.notifications.notify] Traceback ..."

    async def test_in_json_the_traceback_is_a_field(self, caplog, monkeypatch):
        monkeypatch.setattr("app.core.events.worker.json_enabled", lambda: True)

        [record] = await self._handle(_make_event(retry_count=11, max_retries=12), caplog)

        assert "\n" not in record.getMessage()
        assert record.fields == {"exception": "[app.x.notifications.notify] Traceback ..."}

    async def test_the_lines_of_an_event_carry_the_request_that_published_it(self):
        seen: list[str] = []
        event = _make_event()
        event.correlation_id = "trace-abc"

        with (
            patch("app.core.events.worker.dispatcher.dispatch", return_value=self._FAILED),
            patch(
                "app.core.events.worker.logger.warning",
                side_effect=lambda *a, **k: seen.append(request_id_var.get()),
            ),
        ):
            await OutboxWorker()._handle_event(AsyncMock(), event)

        assert seen == ["trace-abc"]
        assert request_id_var.get() == "", "reset once the event is handled"


class TestWhatTheListenerLogs:
    async def _run_once(self, error: Exception, caplog) -> list:
        worker = OutboxWorker()

        async def stop_instead_of_waiting(_delay):
            worker._shutdown_event.set()

        with (
            patch("app.core.events.worker.asyncpg.connect", side_effect=error),
            patch("app.core.events.worker.asyncio.sleep", side_effect=stop_instead_of_waiting),
            caplog.at_level("INFO", logger="app.core.events.worker"),
        ):
            await worker._run()
        return [r for r in caplog.records if r.name == "app.core.events.worker"]

    async def test_a_database_that_does_not_answer_is_one_line_per_attempt(self, caplog):
        [record] = await self._run_once(ConnectionRefusedError("refused"), caplog)

        assert record.levelname == "WARNING"
        assert record.exc_info is None
        assert record.getMessage() == (
            "Outbox worker cannot reach the database (ConnectionRefusedError: refused), "
            "retrying in 2s"
        )

    async def test_any_other_error_keeps_its_traceback(self, caplog):
        # A bug in the worker must not hide behind a reconnection line.
        [record] = await self._run_once(RuntimeError("bug"), caplog)

        assert record.levelname == "ERROR"
        assert record.exc_info is not None
