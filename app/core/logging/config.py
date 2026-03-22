import json
import logging
import logging.config
import traceback
from datetime import UTC, datetime

from app.core.config import settings

try:
    import colorlog  # noqa: F401

    _has_colorlog = True
except ImportError:
    _has_colorlog = False


class JSONFormatter(logging.Formatter):
    """Serializes LogRecords as single-line JSON for production log aggregators."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "layer": getattr(record, "layer_name", "App"),
            "module": getattr(record, "module_name", record.module),
            "logger": record.name,
            "request_id": getattr(record, "request_id", ""),
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exception"] = "".join(traceback.format_exception(*record.exc_info))
        return json.dumps(entry, default=str)


def setup_logging() -> None:
    env = settings.ENVIRONMENT.lower()
    log_format = settings.LOG_FORMAT.lower()

    use_json = env not in ("local", "dev") if log_format == "auto" else log_format == "json"

    use_color = not use_json and _has_colorlog and env in ("local", "dev")

    if use_json:
        formatter_config: dict = {
            "()": "app.core.logging.config.JSONFormatter",
        }
    elif use_color:
        fmt = (
            "%(log_color)s%(levelname)s%(reset)s: "
            "[%(colored_layer)s] "
            "[%(colored_module)s] "
            "[%(request_id)s] "
            "%(log_color)s❯%(reset)s %(message)s"
        )
        formatter_config = {
            "()": "colorlog.ColoredFormatter",
            "format": fmt,
            "log_colors": {
                "DEBUG": "white",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        }
    else:
        fmt = (
            "%(asctime)s %(levelname)s: [%(layer_name)s] [%(module_name)s]"
            " [%(request_id)s] ❯ %(message)s"
        )
        formatter_config = {
            "()": "logging.Formatter",
            "format": fmt,
            "datefmt": "%Y-%m-%d %H:%M:%S",
        }

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "layer_module": {"()": "app.core.logging.filters.LayerModuleFilter"},
            "request_id": {"()": "app.core.logging.filters.RequestIdFilter"},
            "ignore_options": {"()": "app.core.logging.filters.IgnoreOptionsFilter"},
            "ignore_healthcheck": {"()": "app.core.logging.filters.IgnoreHealthcheckFilter"},
        },
        "formatters": {
            "default": formatter_config,
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["layer_module", "request_id", "ignore_options"],
                "level": "DEBUG",
            },
        },
        "loggers": {
            "app": {
                "handlers": ["console"],
                "level": settings.LOG_LEVEL.upper(),
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["console"],
                "filters": ["ignore_options", "ignore_healthcheck"],
                "level": "INFO",
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["console"],
            "level": "WARNING",
        },
    }

    logging.config.dictConfig(config)
