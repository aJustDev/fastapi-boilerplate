import uuid
from unittest.mock import AsyncMock

from app.core.events.bus import EventBus
from app.models.events.outbox import OutboxEventORM


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
        assert "NOTIFY" in str(text_clause)

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
        agg_id = uuid.uuid4()
        corr_id = uuid.uuid4()

        await bus.publish(
            "order.created",
            {"order_id": 1},
            aggregate_id=agg_id,
            correlation_id=corr_id,
        )

        event = mock_session.add.call_args[0][0]
        assert event.aggregate_id == agg_id
        assert event.correlation_id == corr_id

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
