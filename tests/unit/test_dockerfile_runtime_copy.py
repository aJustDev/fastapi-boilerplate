"""The runtime stage of the Dockerfile copies an allow-list, and the list stays valid.

`COPY . .` is a deny-list: any new file lands in the image unless someone remembers to
add it to .dockerignore. With an allow-list the mistake shows the other way round (the
file is missing and something fails), which is the failure we want.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def runtime_copy_sources(dockerfile: str) -> list[str]:
    """Build-context paths that COPY or ADD bring into the stage `AS runtime`.

    Without flags, destinations and copies from another stage (`--from`).
    """
    in_runtime = False
    sources: list[str] = []
    for line in dockerfile.splitlines():
        clean = line.strip()
        if clean.upper().startswith("FROM "):
            in_runtime = clean.upper().endswith(" AS RUNTIME")
            continue
        if in_runtime and clean.upper().startswith(("COPY ", "ADD ")):
            args = clean.split()[1:]
            if any(a.startswith("--from=") for a in args):
                continue
            sources.extend(a for a in args[:-1] if not a.startswith("--"))
    return sources


def is_whole_context(source: str) -> bool:
    """`.`, `./`, `./.`, `*`, `./*`: every way of saying "everything"."""
    return source.strip("./") in ("", "*")


def _runtime_copy_sources() -> list[str]:
    return runtime_copy_sources(DOCKERFILE.read_text())


def test_scanner_sees_the_runtime_copies():
    # Canary: if the parser stops finding COPY lines, the other tests pass vacuously.
    assert "app" in _runtime_copy_sources()


def test_runtime_does_not_copy_the_whole_context():
    assert not [s for s in _runtime_copy_sources() if is_whole_context(s)]


@pytest.mark.parametrize(
    "line", ["COPY . .", "COPY ./ /app/", "COPY ./. /app/", "ADD . /app", "COPY * /app/"]
)
def test_detector_catches_every_spelling_of_the_whole_context(line: str):
    sources = runtime_copy_sources(f"FROM python AS runtime\n{line}\n")
    assert sources and all(is_whole_context(s) for s in sources), line


def test_detector_ignores_other_stages_and_stage_copies():
    dockerfile = (
        "FROM python AS builder\nCOPY . .\nFROM python AS runtime\nCOPY --from=builder /a /a\n"
    )
    assert runtime_copy_sources(dockerfile) == []


def test_every_copied_path_exists():
    missing = [s for s in _runtime_copy_sources() if not (ROOT / s).exists()]
    assert not missing, f"the Dockerfile copies paths that do not exist: {missing}"


def test_copied_paths_are_not_dockerignored():
    # A COPY of an ignored path fails only when the image is built.
    entries = [
        clean
        for line in DOCKERIGNORE.read_text().splitlines()
        if (clean := line.strip()) and not clean.startswith("#")
    ]
    ignored = {e.rstrip("/") for e in entries if not e.startswith("!")}
    negated = {e[1:].rstrip("/") for e in entries if e.startswith("!")}

    blocked = [
        s for s in _runtime_copy_sources() if s.split("/")[0] in ignored and s not in negated
    ]
    assert not blocked, f"the Dockerfile copies paths excluded by .dockerignore: {blocked}"
