"""What `setup_logging()` installs, read from the configuration it hands to dictConfig.

The suite already runs under the configuration main.py applied at import; these tests
build others (JSON, plain text) without installing them.
"""

import logging
from unittest.mock import patch

from app.core.logging.config import setup_logging
from app.core.logging.filters import LayerModuleFilter, RequestIdFilter


def _config(monkeypatch, log_format: str) -> dict:
    monkeypatch.setattr("app.core.logging.config.settings.ENVIRONMENT", "production")
    monkeypatch.setattr("app.core.logging.config.settings.LOG_FORMAT", log_format)
    with patch("app.core.logging.config.logging.config.dictConfig") as dict_config:
        setup_logging()
    return dict_config.call_args.args[0]


def test_uvicorn_says_where_it_listens(monkeypatch):
    # "Uvicorn running on http://..." and the startup and shutdown lines are INFO.
    assert _config(monkeypatch, "json")["loggers"]["uvicorn"]["level"] == "INFO"


def test_a_line_outside_a_request_has_no_empty_brackets(monkeypatch):
    formatter = logging.Formatter(_config(monkeypatch, "text")["formatters"]["default"]["format"])
    record = logging.LogRecord("app.core.startup", logging.INFO, "", 0, "hello", (), None)
    LayerModuleFilter().filter(record)
    RequestIdFilter().filter(record)

    line = formatter.format(record)

    assert line.endswith("INFO: [Core] [Startup] ❯ hello")
