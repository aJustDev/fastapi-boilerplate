import json
import logging
import sys

from app.core.logging.config import JSONFormatter


class TestJSONFormatter:
    def _make_record(self, msg: str = "hello", **kwargs) -> logging.LogRecord:
        record = logging.LogRecord(
            name="app.orders.api.router",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        fmt = JSONFormatter()
        record = self._make_record(layer_name="Router", module_name="Orders", request_id="abc")
        line = fmt.format(record)
        data = json.loads(line)
        assert data["message"] == "hello"
        assert data["level"] == "INFO"
        assert data["layer"] == "Router"
        assert data["module"] == "Orders"
        assert data["request_id"] == "abc"
        assert data["logger"] == "app.orders.api.router"
        assert "timestamp" in data

    def test_includes_exception(self):
        fmt = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            record = self._make_record(layer_name="App", module_name="Test", request_id="")
            record.exc_info = sys.exc_info()

        line = fmt.format(record)
        data = json.loads(line)
        assert "exception" in data
        assert "ValueError" in data["exception"]
        assert "boom" in data["exception"]

    def test_missing_custom_attrs_use_defaults(self):
        fmt = JSONFormatter()
        record = self._make_record()
        line = fmt.format(record)
        data = json.loads(line)
        assert data["layer"] == "App"
        assert data["request_id"] == ""

    def test_fields_of_the_record_join_the_line(self):
        record = self._make_record(fields={"startup": {"env": "production"}, "level": "fake"})
        data = json.loads(JSONFormatter().format(record))
        assert data["startup"] == {"env": "production"}
        assert data["level"] == "INFO", "a field must not overwrite a standard key"
