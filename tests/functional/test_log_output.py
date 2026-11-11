"""What a real uvicorn process writes, read from its output.

The configuration is checked elsewhere piece by piece; this is the end result a log
collector receives.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _start_and_stop(**env: str) -> list[str]:
    """Lines a server writes from its start until it says startup is complete."""
    process = subprocess.Popen(  # noqa: S603 -- fixed arguments, the interpreter running the suite
        [sys.executable, "-m", "uvicorn", "main:app", "--port", "0"],
        cwd=ROOT,
        env={
            **os.environ,
            "SETTINGS_ENV_FILE": "",
            "ENVIRONMENT": "local",
            "TZ": "UTC",
            # Nothing listens there: startup goes on without a database, as it must.
            "DB_PORT": "1",
            "OUTBOX_WORKER_ENABLED": "false",
            "JOB_WORKER_ENABLED": "false",
            **env,
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines: list[str] = []
    deadline = time.monotonic() + 30
    try:
        assert process.stdout is not None
        while time.monotonic() < deadline:
            line = process.stdout.readline()
            if not line:
                break
            lines.append(line.rstrip("\n"))
            if "Application startup complete" in line:
                break
    finally:
        process.terminate()
        process.wait(timeout=10)
    return lines


def test_in_json_every_line_is_json_from_the_first_one():
    # Uvicorn writes "Started server process" before the lifespan runs: logging is set up
    # when the app is built, or those lines come out in uvicorn's own format.
    lines = _start_and_stop(LOG_FORMAT="json")

    assert any("Application startup complete" in line for line in lines), lines
    for line in lines:
        record = json.loads(line)
        assert {"timestamp", "level", "message"} <= record.keys()
    assert json.loads(lines[0])["message"].startswith("Started server process")
