"""How many processes the server has, counted by processes that are really started.

The count goes in the title of the startup table and multiplies the connection budget of
its `Capacity` row.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _output(*command: str) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed commands, the interpreter running the suite
        command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_a_process_started_alone_does_not_count_the_other_children_of_its_parent():
    # `uvicorn main:app` from a shell with another job running is one process, not two.
    count = "from app.core.startup import _count_sibling_workers as c; print(c())"
    shell = f'sleep 30 >/dev/null 2>&1 & "{sys.executable}" -c "{count}"; kill $!'

    assert _output("sh", "-c", shell) == "1"


def test_the_workers_uvicorn_starts_count_each_other():
    assert _output(sys.executable, "-m", "tests.functional.process_count_workers") == "[3, 3, 3]"
