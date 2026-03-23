from unittest.mock import MagicMock

from prometheus_client import REGISTRY

from app.core.metrics.db_collector import update_db_pool_metrics
from app.core.metrics.instruments import (
    db_pool_checked_in,
    db_pool_checked_out,
    db_pool_overflow,
    db_pool_size,
    http_request_duration_seconds,
    http_requests_in_progress,
    http_requests_total,
)


class TestMetricsRegistered:
    """Verify all expected metrics are registered in the default Prometheus registry."""

    def test_http_requests_total_registered(self):
        assert "http_requests_total" in REGISTRY._names_to_collectors

    def test_http_request_duration_registered(self):
        assert "http_request_duration_seconds" in REGISTRY._names_to_collectors

    def test_http_requests_in_progress_registered(self):
        assert "http_requests_in_progress" in REGISTRY._names_to_collectors

    def test_db_pool_gauges_registered(self):
        assert "db_pool_size" in REGISTRY._names_to_collectors
        assert "db_pool_checked_out" in REGISTRY._names_to_collectors
        assert "db_pool_checked_in" in REGISTRY._names_to_collectors
        assert "db_pool_overflow" in REGISTRY._names_to_collectors

    def test_http_requests_total_has_correct_labels(self):
        assert http_requests_total._labelnames == ("method", "path_template", "status")

    def test_http_request_duration_has_correct_labels(self):
        assert http_request_duration_seconds._labelnames == ("method", "path_template")

    def test_http_requests_in_progress_has_correct_labels(self):
        assert http_requests_in_progress._labelnames == ("method",)


class TestDbPoolCollector:
    def test_update_db_pool_metrics_sets_gauges(self):
        mock_engine = MagicMock()
        mock_engine.pool.size.return_value = 5
        mock_engine.pool.checkedout.return_value = 2
        mock_engine.pool.checkedin.return_value = 3
        mock_engine.pool.overflow.return_value = 1

        update_db_pool_metrics(mock_engine)

        assert db_pool_size._value.get() == 5.0
        assert db_pool_checked_out._value.get() == 2.0
        assert db_pool_checked_in._value.get() == 3.0
        assert db_pool_overflow._value.get() == 1.0
