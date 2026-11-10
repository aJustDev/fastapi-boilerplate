"""No SQL in app/ is built by pasting strings together.

Today everything goes through the ORM or `text()` with fixed literals and named
parameters; this test keeps it that way. It checks the form (f-string, `%`, `+`,
`.format()`/`.join()` reaching a call that takes SQL), not exploitability, so
interpolating a module constant also fails and needs an ALLOWED entry.

If it fails, use a named parameter:

    await session.execute(text("SELECT ... WHERE id = :id"), {"id": value})

If an identifier really has to be interpolated (it cannot be a parameter), add it to
ALLOWED with the reason; the value must come from an allow-list in the code, never from
the request.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[2] / "app"

# Calls that take SQL text: SQLAlchemy (`text`, `literal_column`, `execute`,
# `exec_driver_sql`) and asyncpg connections (`fetch*`, `executemany`).
SQL_CALLS = frozenset(
    {
        "text",
        "literal_column",
        "execute",
        "exec_driver_sql",
        "executemany",
        "fetch",
        "fetchrow",
        "fetchval",
    }
)
# Keyword names under which the SQL can be passed instead of positionally.
SQL_KEYWORDS = frozenset({"text", "statement", "query", "sql"})

# (path relative to app/, called name) -> reason.
ALLOWED: dict[tuple[str, str], str] = {}

Scope = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef


def _is_interpolated(node: ast.expr) -> bool:
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod | ast.Add):
        return True
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "format":
            return True
        # ", ".join(parts) and sep.join(parts) build a string. A `.join()` on the result
        # of a call is the JOIN of a statement: select(A).join(B).
        if node.func.attr == "join" and not isinstance(node.func.value, ast.Call):
            return True
        # A method called on a built string: f"...".strip()
        return _is_interpolated(node.func.value)
    return False


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _built_names(scope: Scope) -> set[str]:
    """Names that hold a string built by interpolation somewhere in `scope`."""
    names: set[str] = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and _is_interpolated(node.value):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and _is_interpolated(node.value)
            and isinstance(node.target, ast.Name)
        ):
            names.add(node.target.id)
        elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)  # query += "..."
    return names


def _sql_arguments(call: ast.Call) -> list[ast.expr]:
    arguments = call.args[:1]
    arguments += [kw.value for kw in call.keywords if kw.arg in SQL_KEYWORDS]
    return arguments


def scan(source: str, filename: str = "<source>") -> tuple[int, list[str]]:
    """(SQL calls seen, findings) for a piece of source code."""
    tree = ast.parse(source, filename=filename)
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    built: dict[ast.AST, set[str]] = {}

    def is_built(name: str, node: ast.AST) -> bool:
        current: ast.AST | None = node
        while current is not None:
            if isinstance(current, Scope):
                if current not in built:
                    built[current] = _built_names(current)
                if name in built[current]:
                    return True
            current = parents.get(current)
        return False

    seen, findings = 0, []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _called_name(node) not in SQL_CALLS:
            continue
        seen += 1
        for argument in _sql_arguments(node):
            if _is_interpolated(argument) or (
                isinstance(argument, ast.Name) and is_built(argument.id, node)
            ):
                findings.append(f"{node.lineno} {_called_name(node)}({ast.unparse(argument)[:60]})")
    return seen, findings


def _app_findings() -> tuple[int, list[str]]:
    total, found = 0, []
    for path in sorted(APP.rglob("*.py")):
        rel = path.relative_to(APP).as_posix()
        seen, findings = scan(path.read_text(), str(path))
        total += seen
        found += [
            f"app/{rel}:{finding}"
            for finding in findings
            if (rel, finding.split(" ", 1)[1].split("(", 1)[0]) not in ALLOWED
        ]
    return total, found


@pytest.mark.parametrize(
    "source",
    [
        'text(f"SELECT {x}")',
        'text("SELECT " + x)',
        'text("SELECT %s" % x)',
        'text("SELECT {}".format(x))',
        'text(", ".join(parts))',
        "text(sep.join(parts))",
        'q = " AND ".join(parts)\ntext(q)',
        'text(f"SELECT {x}".strip())',
        'text(text=f"SELECT {x}")',
        'literal_column(f"{x}")',
        'conn.fetch(f"SELECT {x}")',
        'conn.execute(f"SELECT {x}")',
        'q = f"SELECT {x}"\ntext(q)',
        'def f(x):\n    q = "SELECT " + x\n    return text(q)',
        'def f(x):\n    q = "SELECT 1"\n    q += x\n    return text(q)',
        'Q = f"SELECT {x}"\ndef f():\n    return text(Q)',
    ],
)
def test_detector_catches(source: str):
    # Canaries: each is a way of building SQL from strings that must not get through.
    assert scan(source)[1], source


@pytest.mark.parametrize(
    "source",
    [
        'text("SELECT 1 WHERE id = :id")',
        'text(f"SELECT 1")',  # no placeholder: a constant
        'q = "SELECT 1"\ntext(q)',
        "session.execute(select(Model).where(Model.id == value))",
        "session.execute(select(A).join(B, B.a_id == A.id).where(A.at <= now() + delta))",
        "stmt = select(A).join(B, B.a_id == A.id).limit(5)\nsession.execute(stmt)",
    ],
)
def test_detector_accepts(source: str):
    assert not scan(source)[1], source


def test_scanner_sees_the_sql_calls_of_the_app():
    # Canary: a rename of app/ or of the calls would leave the test below with nothing.
    assert _app_findings()[0] >= 30


def test_no_interpolated_sql_in_app():
    findings = _app_findings()[1]
    assert not findings, "SQL built from strings:\n  " + "\n  ".join(findings)
