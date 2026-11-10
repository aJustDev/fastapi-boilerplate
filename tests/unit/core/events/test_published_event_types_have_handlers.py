"""Every event type published in app/ has at least one registered handler.

An event nobody handles is retried and ends as FAILED (docs/event-bus.md): it is better
to find the missing import in app/db_registry.py here than in production.
"""

import ast
from pathlib import Path

import app.db_registry  # noqa: F401 -- registers every handler
from app.core.events.dispatcher import dispatcher

APP = Path(__file__).resolve().parents[4] / "app"


def _published_event_types() -> set[str]:
    """Literal event types passed to `.publish(...)`, positionally or as event_type=."""
    found = set()
    for path in APP.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "publish"
            ):
                continue
            candidates = [kw.value for kw in node.keywords if kw.arg == "event_type"]
            candidates += node.args[:1]
            found.update(
                c.value
                for c in candidates
                if isinstance(c, ast.Constant) and isinstance(c.value, str)
            )
    return found


def test_scanner_sees_the_published_events():
    assert {"item.created", "item.updated", "item.deleted"} <= _published_event_types()


def test_every_published_event_type_has_a_handler():
    missing = sorted(t for t in _published_event_types() if not dispatcher._handlers.get(t))
    assert not missing, (
        f"published without handler (missing import in app/db_registry.py?): {missing}"
    )
