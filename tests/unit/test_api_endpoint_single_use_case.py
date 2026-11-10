"""Every HTTP endpoint runs at most one use case.

A router that chains two use cases is orchestrating, which is the use case's job
(docs/architecture.md, ADR-003). If this fails:

- write a composed use case in the owning context that does both steps, or
- publish an event from the first use case and react in an event handler, or
- if the function is not an HTTP endpoint, add (relative path, function name) to
  ALLOWLIST with a comment saying why.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ROUTER_FILES = sorted(
    [*ROOT.glob("app/*/api/*.py"), *ROOT.glob("app/api/v1/*.py")],
)

# (path relative to the repo, function name), each with a comment.
ALLOWLIST: set[tuple[str, str]] = set()


def _is_endpoint(node: ast.AsyncFunctionDef) -> bool:
    return any("router." in ast.unparse(d) for d in node.decorator_list)


def _endpoints() -> list[tuple[str, ast.AsyncFunctionDef]]:
    found = []
    for path in ROUTER_FILES:
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and _is_endpoint(node):
                found.append((str(path.relative_to(ROOT)), node))
    return found


def _use_case_calls(fn: ast.AsyncFunctionDef) -> list[str]:
    """Calls to `.execute(...)`, the entry point of every use case."""
    return [
        f"line {sub.lineno}: {ast.unparse(sub)}"
        for sub in ast.walk(fn)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Attribute)
        and sub.func.attr == "execute"
    ]


ENDPOINTS = _endpoints()


def test_scanner_sees_the_api():
    # Canary: if the router layout changes and nothing is found, the test below passes
    # vacuously.
    names = {fn.name for _, fn in ENDPOINTS}
    assert {"login", "create_item"} <= names


@pytest.mark.parametrize(("path", "fn"), ENDPOINTS, ids=[f"{p}::{f.name}" for p, f in ENDPOINTS])
def test_endpoint_runs_at_most_one_use_case(path: str, fn: ast.AsyncFunctionDef):
    if (path, fn.name) in ALLOWLIST:
        pytest.skip("allowlisted")
    calls = _use_case_calls(fn)
    assert len(calls) <= 1, f"{path}::{fn.name} runs {len(calls)} use cases:\n  " + "\n  ".join(
        calls
    )
