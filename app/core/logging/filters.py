import logging

LAYER_MAP = {
    "api": ("Router", "light_green"),
    "use_cases": ("UseCase", "bold_blue"),
    "services": ("Service", "yellow"),
    "repos": ("Repo", "purple"),
    "core": ("Core", "cyan"),
    "deps": ("Deps", "white"),
    "jobs": ("Job", "light_blue"),
    "event_handlers": ("Handler", "light_purple"),
}

LAYER_COLORS = {
    "Router": "light_green",
    "UseCase": "bold_blue",
    "Service": "yellow",
    "Repo": "purple",
    "Core": "cyan",
    "Deps": "white",
    "Job": "light_blue",
    "Handler": "light_purple",
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
    "light_blue": "\033[94m",
    "light_purple": "\033[95m",
}
ANSI_RESET = "\033[0m"


class LayerModuleFilter(logging.Filter):
    """Extracts architectural layer and module from logger path.

    No fixed padding: each name takes its natural width.
    Module name is title-cased for readability.
    """

    # Loggers whose module name says little on its own: two workers would both be
    # [Core] [Worker], and the exception handlers [Core] [Handlers], like event handlers.
    LOGGER_OVERRIDES: dict[str, tuple[str, str]] = {
        "uvicorn.error": ("App", "Server"),
        "app.core.events.worker": ("Core", "Outbox"),
        "app.core.events.cleanup": ("Core", "Outbox"),
        "app.core.jobs.worker": ("Core", "Jobs"),
        "app.core.exceptions.handlers": ("Core", "Errors"),
        "app.core.exceptions.middleware": ("Core", "Errors"),
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

            # app.<context>.api.router: every router file has the same name, the
            # context says which one logged.
            if module_name == "router" and "api" in parts[1:]:
                module_name = parts[parts.index("api") - 1]

        clean_module = module_name.replace("_", " ").title()

        record.layer_name = layer_name
        record.module_name = clean_module

        layer_color = ANSI_CODES.get(LAYER_COLORS.get(layer_name, "white"), "")
        module_color = ANSI_CODES.get(MODULE_COLOR, "")
        record.colored_layer = f"{layer_color}{layer_name}{ANSI_RESET}"
        record.colored_module = f"{module_color}{clean_module}{ANSI_RESET}"

        return True


class RequestIdFilter(logging.Filter):
    """Injects request_id from ContextVar into every LogRecord.

    `request_tag` is what the text formats print: `[<id>] ` during a request, nothing
    outside one (startup, jobs), where empty brackets would only be noise.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from app.core.logging.context import get_request_id

        request_id = get_request_id()
        record.request_id = request_id
        record.request_tag = f"[{request_id}] " if request_id else ""
        return True
