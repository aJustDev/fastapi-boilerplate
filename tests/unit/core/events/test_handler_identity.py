"""Two handlers are two handlers, whatever their functions are called.

Contexts react to the same event with their own handlers, and naming them after the
event is the obvious convention: `on_order_paid` in billing and in notifications.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.core.events.dispatcher import EventDispatcher
from app.core.events.models import OutboxEventORM
from app.core.events.worker import OutboxWorker


def _event() -> OutboxEventORM:
    return OutboxEventORM(
        id=uuid.uuid4(),
        event_type="order.paid",
        payload={"order_id": 1},
        status="PENDING",
        retry_count=0,
        max_retries=5,
        scheduled_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        handler_state={},
    )


async def test_a_failed_handler_is_retried_even_if_a_namesake_succeeded():
    dispatcher = EventDispatcher()
    calls = {"billing": 0, "notifications": 0}
    billing_is_down = True

    def billing_module() -> None:
        @dispatcher.register("order.paid")
        async def on_order_paid(payload: dict, *_: object) -> None:
            calls["billing"] += 1
            if billing_is_down:
                raise RuntimeError("billing provider down")

    def notifications_module() -> None:
        @dispatcher.register("order.paid")
        async def on_order_paid(payload: dict, *_: object) -> None:
            calls["notifications"] += 1

    billing_module()
    notifications_module()
    event, worker, session = _event(), OutboxWorker(), AsyncMock()

    with patch("app.core.events.worker.dispatcher", dispatcher):
        await worker._handle_event(session, event)
        assert event.status == "PENDING"

        billing_is_down = False
        await worker._handle_event(session, event)

    assert event.status == "PROCESSED"
    assert calls == {"billing": 2, "notifications": 1}  # retried; the other one not repeated
    assert len(event.handler_state) == 2


def test_registering_the_same_handler_twice_for_an_event_is_an_error():
    dispatcher = EventDispatcher()

    async def notify(payload: dict, *_: object) -> None: ...

    dispatcher.register("order.paid")(notify)
    with pytest.raises(ValueError, match="already registered"):
        dispatcher.register("order.paid")(notify)


def test_one_function_may_handle_several_events():
    dispatcher = EventDispatcher()

    async def audit(payload: dict, *_: object) -> None: ...

    dispatcher.register("order.paid")(audit)
    dispatcher.register("order.refunded")(audit)

    assert set(dispatcher.registered_events) == {"order.paid", "order.refunded"}
