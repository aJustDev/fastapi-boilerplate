import logging

LAYER_MAP = {
    "api": ("Router", "light_green"),
    "use_cases": ("UseCase", "bold_blue"),
    "services": ("Service", "yellow"),
    "repos": ("Repo", "purple"),
    "core": ("Core", "cyan"),
    "deps": ("Deps", "white"),
}

LAYER_COLORS = {
    "Router": "light_green",
    "UseCase": "bold_blue",
    "Service": "yellow",
    "Repo": "purple",
    "Core": "cyan",
    "Deps": "white",
    "App": "white",
}

MODULE_COLOR = "cyan"

ANSI_CODES = {
    "light_green": "\033[32m",
    "bold_blue": "\033[34m",
    "yellow": "\033[33m",
    "purple": "\033[35m",
    "cyan": "\033[36m",
    "white": "\033[37m",
}
ANSI_RESET = "\033[0m"


class LayerModuleFilter(logging.Filter):
    """Extracts architectural layer and module from logger path.

    No fixed padding — natural width like siba.
    Module name is title-cased for readability.
    """

    # Map full logger names to friendly display names
    LOGGER_OVERRIDES: dict[str, tuple[str, str]] = {
        "uvicorn.error": ("App", "Server"),
        "uvicorn.access": ("App", "Access"),
    }

    def filter(self, record: logging.LogRecord) -> bool:
        parts = record.name.split(".")

        if record.name in self.LOGGER_OVERRIDES:
            layer_name, module_name = self.LOGGER_OVERRIDES[record.name]
        else:
            layer_name = "App"
            module_name = parts[-1] if len(parts) > 1 else record.name

            for part in parts:
                if part in LAYER_MAP:
                    display, _ = LAYER_MAP[part]
                    layer_name = display
                    break

        clean_module = module_name.replace("_", " ").title()

        record.layer_name = layer_name
        record.module_name = clean_module

        layer_color = ANSI_CODES.get(LAYER_COLORS.get(layer_name, "white"), "")
        module_color = ANSI_CODES.get(MODULE_COLOR, "")
        record.colored_layer = f"{layer_color}{layer_name}{ANSI_RESET}"
        record.colored_module = f"{module_color}{clean_module}{ANSI_RESET}"

        return True


class IgnoreOptionsFilter(logging.Filter):
    """Suppresses OPTIONS request logs to reduce noise."""

    def filter(self, record: logging.LogRecord) -> bool:
        return '"OPTIONS' not in record.getMessage()


class IgnoreHealthcheckFilter(logging.Filter):
    """Suppresses healthcheck endpoint logs to reduce noise."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/health/liveness" not in record.getMessage()


class RequestIdFilter(logging.Filter):
    """Injects request_id from ContextVar into every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:
        from app.core.logging.context import get_request_id

        record.request_id = get_request_id()
        return True
