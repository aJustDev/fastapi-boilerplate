import re
from pathlib import Path

from app.core.config import Settings

ENV_EXAMPLE = Path(__file__).parents[3] / ".env.example"

# A key counts as documented when it appears active (`KEY=`) or commented (`# KEY=`).
_KEY_RE = re.compile(r"^#? ?([A-Z][A-Z0-9_]*)=", re.MULTILINE)


def test_env_example_matches_settings():
    documented = set(_KEY_RE.findall(ENV_EXAMPLE.read_text()))
    fields = set(Settings.model_fields)

    missing = sorted(fields - documented)
    unknown = sorted(documented - fields)
    assert not missing, f"Settings fields missing from .env.example: {missing}"
    assert not unknown, f".env.example keys that Settings does not define: {unknown}"
