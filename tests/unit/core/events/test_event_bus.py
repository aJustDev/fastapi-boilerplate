from unittest.mock import AsyncMock, patch

from app.core.events.bus import EventBus
from app.core.events.models import OutboxEventORM
from app.core.logging.context import request_id_var


class TestEventBus:
    async def test_publish_inserts_and_notifies(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)

        await bus.publish("order.created", {"order_id": 42})

        # Verify add was called with an OutboxEventORM
        mock_session.add.assert_called_once()
        event = mock_session.add.call_args[0][0]
        assert isinstance(event, OutboxEventORM)
        assert event.event_type == "order.created"
        assert event.payload == {"order_id": 42}

        # Verify flush and refresh were called
        mock_session.flush.assert_called_once()
        mock_session.refresh.assert_called_once_with(event)

        # Verify NOTIFY was sent
        mock_session.execute.assert_called_once()
        text_clause = mock_session.execute.call_args[0][0]
        assert "pg_notify" in str(text_clause)

        # Verify commit was NOT called
        mock_session.commit.assert_not_called()

    async def test_publish_returns_event(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)

        result = await bus.publish("test.event", {"data": "value"})

        assert isinstance(result, OutboxEventORM)
        assert result.event_type == "test.event"
        assert result.payload == {"data": "value"}

    async def test_publish_with_aggregate_and_correlation(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)

        await bus.publish(
            "order.created",
            {"order_id": 1},
            aggregate_id=42,
            correlation_id="trace-1",
        )

        event = mock_session.add.call_args[0][0]
        assert event.aggregate_id == "42"  # the id of the entity, as text
        assert event.correlation_id == "trace-1"

    async def test_correlation_defaults_to_the_current_request(self, mock_session: AsyncMock):
        token = request_id_var.set("req-7")
        try:
            await EventBus(mock_session).publish("order.created", {})
        finally:
            request_id_var.reset(token)

        assert mock_session.add.call_args[0][0].correlation_id == "req-7"

    async def test_publish_without_optional_ids(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)

        await bus.publish("test.event", {})

        event = mock_session.add.call_args[0][0]
        assert event.aggregate_id is None
        assert event.correlation_id is None

    async def test_publish_preserves_payload(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)
        payload = {"nested": {"key": [1, 2, 3]}, "flag": True}

        await bus.publish("complex.event", payload)

        event = mock_session.add.call_args[0][0]
        assert event.payload == payload

    async def test_publish_applies_the_configured_max_retries(self, mock_session: AsyncMock):
        with patch("app.core.events.bus.settings.OUTBOX_MAX_RETRIES", 9):
            event = await EventBus(mock_session).publish("test.event", {})

        assert event.max_retries == 9


class TestPublishMany:
    async def test_inserts_one_event_per_pair_and_notifies_once(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)

        published = await bus.publish_many(
            "seat.freed", [(1, {"seat": "a"}), ("x-2", {"seat": "b"}), (None, {"seat": "c"})]
        )

        assert published == 3
        events = mock_session.add_all.call_args[0][0]
        assert [e.event_type for e in events] == ["seat.freed"] * 3
        assert [e.aggregate_id for e in events] == ["1", "x-2", None]
        assert [e.payload for e in events] == [{"seat": "a"}, {"seat": "b"}, {"seat": "c"}]
        mock_session.flush.assert_called_once()
        mock_session.execute.assert_called_once()  # a single NOTIFY, whatever the number
        assert "pg_notify" in str(mock_session.execute.call_args[0][0])
        mock_session.commit.assert_not_called()

    async def test_nothing_to_publish_touches_nothing(self, mock_session: AsyncMock):
        bus = EventBus(mock_session)

        assert await bus.publish_many("seat.freed", []) == 0

        mock_session.add_all.assert_not_called()
        mock_session.execute.assert_not_called()

    async def test_events_carry_the_request_id(self, mock_session: AsyncMock):
        token = request_id_var.set("req-7")
        try:
            await EventBus(mock_session).publish_many("seat.freed", [(1, {})])
        finally:
            request_id_var.reset(token)

        (event,) = mock_session.add_all.call_args[0][0]
        assert event.correlation_id == "req-7"
