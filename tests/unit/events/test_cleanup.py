import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.events.cleanup import cleanup_processed_events, replay_failed_events


class TestCleanupProcessedEvents:
    async def test_deletes_old_processed_events(self):
        mock_result = MagicMock()
        mock_result.rowcount = 50  # less than batch size → single pass

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.events.cleanup.async_session_factory",
            return_value=mock_factory,
        ):
            count = await cleanup_processed_events(days=7)

        assert count == 50
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_batched_deletion(self):
        """When first batch is full, loop continues until partial batch."""
        mock_result_full = MagicMock()
        mock_result_full.rowcount = 1000  # equals batch size → continue

        mock_result_partial = MagicMock()
        mock_result_partial.rowcount = 200  # less than batch → stop

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=[mock_result_full, mock_result_partial])
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.events.cleanup.async_session_factory",
            return_value=mock_factory,
        ):
            count = await cleanup_processed_events()

        assert count == 1200
        assert mock_session.execute.call_count == 2
        assert mock_session.commit.call_count == 2


class TestReplayFailedEvents:
    async def test_replays_all_failed(self):
        mock_result = MagicMock()
        mock_result.rowcount = 3

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "app.core.events.cleanup.async_session_factory",
            return_value=mock_factory,
        ):
            count = await replay_failed_events()

        assert count == 3
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    async def test_replays_specific_events(self):
        mock_result = MagicMock()
        mock_result.rowcount = 2

        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        mock_factory = MagicMock()
        mock_factory.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.__aexit__ = AsyncMock(return_value=False)

        event_ids = [uuid.uuid4(), uuid.uuid4()]

        with patch(
            "app.core.events.cleanup.async_session_factory",
            return_value=mock_factory,
        ):
            count = await replay_failed_events(event_ids=event_ids)

        assert count == 2
