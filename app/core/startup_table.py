"""How the startup log reads: one line for JSON, a framed table for a terminal.

Pure functions of the facts `app/core/startup.py` gathers; nothing here asks the database
or the settings.
"""

from typing import Any

from app.core.logging.middleware import METRICS_PATH

# What main.py serves when DOCS_ENABLED is set.
DOCS_PATH = "/docs"


# The state column: green when it works, yellow when it needs a look, red when it does not
# work, grey for what is turned off. SGR codes, used only on a color terminal.
_TONES = {"ok": "32", "on": "36", "wait": "33", "warn": "33", "down": "31", "off": "90"}
_WORKER_STATES = {"started": "ok", "waiting for the database": "wait", "disabled": "off"}
_WORKER_VALUES = {"wait": "waiting for the database", "off": "not in this process"}


def _paint(text: str, sgr: str, color: bool) -> str:
    return f"\033[{sgr}m{text}\033[0m" if color and sgr else text


def _about(facts: dict[str, Any]) -> str:
    parts = [facts["env"], f"log {facts['log_level']}", f"pid {facts['pid']} on {facts['host']}"]
    if facts["processes"] > 1:
        parts.append(f"{facts['processes']} processes")
    return " | ".join(parts)


def header(facts: dict[str, Any]) -> str:
    """The startup log in one line: the message of the JSON record."""
    return f"{facts['app']} v{facts['version']} | {_about(facts)}"


def _database(db: dict[str, Any], pool: dict[str, Any]) -> tuple[str, str]:
    where = f"{db['address']}/{db['name']}"
    if db["status"] != "ok":
        return "down", f"{where}, not answering"
    schema, expected = db["schema"], db["expected"]
    current = f"schema {', '.join(schema)}" if schema else "no schema"
    if schema is not None and expected is not None and schema != expected:
        return "warn", f"{where}, {current}, code expects {', '.join(expected)}"
    # A schema that matches the code is what `ok` says; the revision is shown only when there
    # is nothing to compare it with.
    shown = f", {current}" if schema is not None and expected is None else ""
    pool_size = f"pool {pool['size']} + {pool['overflow']} overflow, timeout {pool['timeout_s']}s"
    return "ok", f"{where}, {pool_size}{shown}"


def _connections(db: dict[str, Any]) -> tuple[str, str]:
    """Whether this instance alone fits in what the server takes (it cannot see replicas)."""
    reach = f"up to {db['instance_max']} from this instance"
    capacity = db["capacity"]
    if capacity is None:
        return "", reach
    allowed = capacity["max"] - capacity["reserved"]
    state = "warn" if db["instance_max"] > allowed else "ok"
    return state, f"{reach}, {capacity['in_use']} of {capacity['max']} in use"


def _worker(status: str, running: str) -> tuple[str, str]:
    state = _WORKER_STATES[status]
    return state, _WORKER_VALUES.get(state, running)


def _switch(enabled: bool, value: str) -> tuple[str, str]:
    return ("on", value) if enabled else ("off", "")


def _rows(facts: dict[str, Any]) -> list[tuple[str, str, str]]:
    """(state, label, value) of each line."""
    limits, metrics = facts["rate_limit"], facts["metrics"]
    token = "token required" if metrics["token"] else "no token"
    lines = {
        "Database": _database(facts["db"], facts["pool"]),
        # Behind a pooler the server's limit is the pooler's business, not this budget.
        **(
            {"Pooler": ("ok", "transaction mode, LISTEN and migrations direct")}
            if facts["db"]["pooler"]
            else {"Capacity": _connections(facts["db"])}
        ),
        "Outbox": _worker(facts["outbox"], "listening for events"),
        "Jobs": _worker(facts["jobs"]["status"], f"{facts['jobs']['handlers']} handlers"),
        "Limits": _switch(
            limits["enabled"],
            f"{limits['default']}, strict {limits['strict']}, in memory per process",
        ),
        "Docs": _switch(facts["docs"], DOCS_PATH),
        "Metrics": _switch(metrics["enabled"], f"{METRICS_PATH}, {token}"),
    }
    return [(state, label, value) for label, (state, value) in lines.items()]


# Box drawing for the table; it is printed only in the text formats.
_H, _V = "\u2500", "\u2502"
_TOP, _BOTTOM = ("\u250c", "\u2510"), ("\u2514", "\u2534", "\u2518")
_SPLIT = ("\u251c", "\u252c", "\u2524")
_STATE_WIDTH = 4


def table(facts: dict[str, Any], *, color: bool = False) -> list[str]:
    """The startup log as a framed table: a title line, then one row per piece."""
    rows = _rows(facts)
    title, about = f"{facts['app']} v{facts['version']}", _about(facts)
    label_width = max(len(label) for _, label, _ in rows)
    # Inner width: the three columns with one space of padding each side and the two
    # separators between them, widened if the title line needs more.
    columns = _STATE_WIDTH + 2 + label_width + 2 + 2
    value_width = max(max(len(value) for *_, value in rows), len(title) + len(about) + 5 - columns)
    widths = [_STATE_WIDTH + 2, label_width + 2, value_width + 2]
    inner = sum(widths) + 2

    def frame(text: str) -> str:  # the frame recedes; the content is what is read
        return _paint(text, "90", color)

    gap = " " * (inner - 2 - len(title) - len(about))
    lines = [
        frame(_TOP[0] + _H * inner + _TOP[1]),
        f"{frame(_V)} {_paint(title, '1', color)}{gap}{about} {frame(_V)}",
        frame(_SPLIT[0] + _SPLIT[1].join(_H * w for w in widths) + _SPLIT[2]),
    ]
    for state, label, value in rows:
        tone = "90" if state == "off" else ""  # what is turned off recedes too
        cells = [
            _paint(f"{state:^{_STATE_WIDTH}}", _TONES.get(state, ""), color),
            _paint(f"{label:<{label_width}}", tone, color),
            _paint(f"{value:<{value_width}}", tone, color),
        ]
        lines.append(frame(_V) + frame(_V).join(f" {cell} " for cell in cells) + frame(_V))
    lines.append(frame(_BOTTOM[0] + _BOTTOM[1].join(_H * w for w in widths) + _BOTTOM[2]))
    return [f"  {line}" for line in lines]
