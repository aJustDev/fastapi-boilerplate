"""`scripts/release.py` run for real, with the real uv, in a project of its own.

The rules of a cut are tested on text in `tests/unit/test_release.py`; here, what only a run
shows: the three files that change, and that a refusal changes none.
"""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "release.py"

PYPROJECT = '[project]\nname = "app"\nversion = "0.1.0"\nrequires-python = ">=3.14"\n'
CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n### Added\n\n- The first route (#1).\n"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT)
    (tmp_path / "CHANGELOG.md").write_text(CHANGELOG)
    return tmp_path


def _release(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # No dependencies to resolve and no environment to build: uv only writes its two files.
    env = os.environ | {"UV_NO_SYNC": "1", "UV_OFFLINE": "1"}
    return subprocess.run(  # noqa: S603 -- fixed commands, the interpreter running the suite
        [sys.executable, str(SCRIPT), *args],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _files(project: Path) -> dict[str, str]:
    return {path.name: path.read_text() for path in sorted(project.iterdir()) if path.is_file()}


def _locked_version(project: Path) -> str:
    [package] = tomllib.loads((project / "uv.lock").read_text())["package"]
    return package["version"]


def test_the_first_release_only_cuts_the_changelog(project: Path):
    before = _files(project)

    result = _release(project, "cut", "0.1.0")

    assert result.returncode == 0, result.stderr
    after = _files(project)
    assert after["pyproject.toml"] == before["pyproject.toml"]
    assert set(after) == set(before), "no lock file is written when the version stays"
    assert "## [Unreleased]\n\n## [0.1.0] - " in after["CHANGELOG.md"]
    assert _release(project, "pending").stdout == "0.1.0\n"
    assert _release(project, "notes", "0.1.0").stdout == "### Added\n\n- The first route (#1).\n"


def test_a_later_release_raises_the_version_in_pyproject_and_in_the_lock(project: Path):
    assert _release(project, "cut", "0.1.0").returncode == 0
    changelog = (project / "CHANGELOG.md").read_text()
    (project / "CHANGELOG.md").write_text(
        changelog.replace(
            "## [Unreleased]\n", "## [Unreleased]\n\n### Fixed\n\n- A wrong total (#2).\n", 1
        )
    )

    result = _release(project, "cut", "0.2.0")

    assert result.returncode == 0, result.stderr
    pyproject = tomllib.loads((project / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == "0.2.0"
    assert _locked_version(project) == "0.2.0"
    assert _release(project, "pending").stdout == "0.2.0\n"
    assert _release(project, "notes", "0.2.0").stdout == "### Fixed\n\n- A wrong total (#2).\n"
    assert _release(project, "notes", "0.1.0").stdout == "### Added\n\n- The first route (#1).\n"


def test_a_project_that_never_cut_a_release_has_nothing_pending(project: Path):
    result = _release(project, "pending")

    assert (result.returncode, result.stdout) == (0, "")


@pytest.mark.parametrize("version", ["0.0.9", "v0.2.0"])
def test_a_refused_cut_writes_nothing(project: Path, version: str):
    before = _files(project)

    result = _release(project, "cut", version)

    assert result.returncode == 1
    assert result.stderr.startswith("release: ")
    assert _files(project) == before


def test_outside_a_project_it_says_where_to_run_it(tmp_path: Path):
    result = _release(tmp_path, "pending")

    assert result.returncode == 1
    assert "run it from the repository root" in result.stderr
