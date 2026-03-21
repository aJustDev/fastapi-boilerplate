import logging
import logging.config

from app.core.config import settings

try:
    import colorlog  # noqa: F401

    _has_colorlog = True
except ImportError:
    _has_colorlog = False


def setup_logging() -> None:
    env = settings.ENVIRONMENT.lower()
    use_color = _has_colorlog and env in ("local", "dev")

    if use_color:
        fmt = (
            "%(log_color)s%(levelname)s%(reset)s: "
            "[%(colored_layer)s] "
            "[%(colored_module)s] "
            "%(log_color)s❯%(reset)s %(message)s"
        )
        formatter_class = "colorlog.ColoredFormatter"
        formatter_kwargs = {
            "log_colors": {
                "DEBUG": "white",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold_red",
            },
        }
    else:
        fmt = "%(asctime)s %(levelname)s: [%(layer_name)s] [%(module_name)s] ❯ %(message)s"
        formatter_class = "logging.Formatter"
        formatter_kwargs = {"datefmt": "%Y-%m-%d %H:%M:%S"}

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "layer_module": {"()": "app.core.logging.filters.LayerModuleFilter"},
            "ignore_options": {"()": "app.core.logging.filters.IgnoreOptionsFilter"},
            "ignore_healthcheck": {"()": "app.core.logging.filters.IgnoreHealthcheckFilter"},
        },
        "formatters": {
            "default": {
                "()": formatter_class,
                "format": fmt,
                **formatter_kwargs,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "filters": ["layer_module", "ignore_options"],
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
