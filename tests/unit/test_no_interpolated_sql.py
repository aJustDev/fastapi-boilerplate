"""No SQL in app/ is built by pasting strings together.

Today everything goes through the ORM or `text()` with fixed literals and named
parameters; this test keeps it that way. It checks the form (f-string, `%`, `+`,
`.format()`/`.join()` as the argument of `text()` or `execute()`), not exploitability,
so interpolating a module constant also fails and needs an ALLOWED entry.

If it fails, use a named parameter:

    await session.execute(text("SELECT ... WHERE id = :id"), {"id": value})

If an identifier really has to be interpolated (it cannot be a parameter), add it to
ALLOWED with the reason; the value must come from an allow-list in the code, never from
the request.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"

# Calls whose first argument ends up as SQL.
SQL_CALLS = frozenset({"text", "execute", "exec_driver_sql"})

# (path relative to app/, called name) -> reason.
ALLOWED: dict[tuple[str, str], str] = {}


def _is_interpolated(node: ast.expr) -> bool:
    if isinstance(node, ast.JoinedStr):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"format", "join"}
    )


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _findings() -> list[str]:
    found = []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = _called_name(node)
            if name in SQL_CALLS and _is_interpolated(node.args[0]) and (rel, name) not in ALLOWED:
                found.append(f"app/{rel}:{node.lineno} {name}({ast.unparse(node.args[0])[:60]})")
    return found


def test_detector_catches_an_f_string():
    # Canary: the detector must flag the pattern it exists for.
    call = ast.parse('text(f"SELECT {x}")').body[0].value
    assert isinstance(call, ast.Call) and _is_interpolated(call.args[0])


def test_no_interpolated_sql_in_app():
    assert not _findings(), "SQL built from strings:\n  " + "\n  ".join(_findings())
