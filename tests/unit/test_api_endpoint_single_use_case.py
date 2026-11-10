"""Every HTTP endpoint runs at most one use case.

A router that chains two use cases is orchestrating, which is the use case's job
(docs/architecture.md, ADR-003). If this fails:

- write a composed use case in the owning context that does both steps, or
- publish an event from the first use case and react in an event handler, or
- if the function is not an HTTP endpoint, add (relative path, function name) to
  ALLOWLIST with a comment saying why.

It applies to every function of a router module, not only to the decorated ones: an
endpoint that delegates to a helper next to it must not get around the rule.
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

Function = ast.FunctionDef | ast.AsyncFunctionDef
HTTP_DECORATORS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "api_route", "websocket"}
)


def is_endpoint(node: Function) -> bool:
    """Decorated with `<any router>.<http method>(...)`, sync or async."""
    return any(
        isinstance(decorator, ast.Call)
        and isinstance(decorator.func, ast.Attribute)
        and decorator.func.attr in HTTP_DECORATORS
        for decorator in node.decorator_list
    )


def use_cases_run(fn: Function) -> list[str]:
    """What looks like running a use case: `.execute(...)` calls and `*UseCase` classes."""
    executes = [
        f"line {sub.lineno}: {ast.unparse(sub)[:70]}"
        for sub in ast.walk(fn)
        if isinstance(sub, ast.Call)
        and isinstance(sub.func, ast.Attribute)
        and sub.func.attr == "execute"
    ]
    classes = sorted(
        {sub.id for sub in ast.walk(fn) if isinstance(sub, ast.Name) and sub.id.endswith("UseCase")}
    )
    return executes if len(executes) >= len(classes) else classes


def _functions(source: str) -> list[Function]:
    return [node for node in ast.walk(ast.parse(source)) if isinstance(node, Function)]


def _router_functions() -> list[tuple[str, Function]]:
    return [
        (str(path.relative_to(ROOT)), fn)
        for path in ROUTER_FILES
        for fn in _functions(path.read_text())
    ]


FUNCTIONS = _router_functions()


def test_scanner_sees_the_api():
    # Canary: if the router layout changes and nothing is found, the test below passes
    # vacuously.
    endpoints = {fn.name for _, fn in FUNCTIONS if is_endpoint(fn)}
    assert {"login", "create_item"} <= endpoints
    assert len(endpoints) >= 12


@pytest.mark.parametrize(
    "source",
    [
        "@router.get('/x')\nasync def f(): ...",
        "@router.post('/x')\ndef f(): ...",  # a sync endpoint is an endpoint
        "@items.delete('/x')\nasync def f(): ...",  # whatever the router is called
        "@v2_router.api_route('/x', methods=['GET'])\nasync def f(): ...",
    ],
)
def test_detector_recognises_an_endpoint(source: str):
    assert is_endpoint(_functions(source)[0])


@pytest.mark.parametrize(
    "body",
    [
        "await A(repo).execute(1)\n    await B(repo).execute(2)",
        "await CreateUseCase(repo).run(1)\n    await NotifyUseCase(bus).run(2)",
    ],
)
def test_detector_counts_two_use_cases(body: str):
    fn = _functions(f"async def f():\n    {body}")[0]
    assert len(use_cases_run(fn)) == 2


@pytest.mark.parametrize(
    ("path", "fn"), FUNCTIONS, ids=[f"{path}::{fn.name}" for path, fn in FUNCTIONS]
)
def test_router_function_runs_at_most_one_use_case(path: str, fn: Function):
    if (path, fn.name) in ALLOWLIST:
        pytest.skip("allowlisted")
    calls = use_cases_run(fn)
    assert len(calls) <= 1, f"{path}::{fn.name} runs {len(calls)} use cases:\n  " + "\n  ".join(
        calls
    )
