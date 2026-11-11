"""Cutting a release, and the shape of CHANGELOG.md that `scripts/release.py` relies on.

The version lives in pyproject.toml and the history in CHANGELOG.md. A version raised by hand,
or a section written by hand, leaves the two apart: the release workflow would then publish
nothing, or the wrong notes.
"""

import tomllib
from datetime import date
from pathlib import Path

import pytest

from scripts import release

ROOT = Path(__file__).resolve().parents[2]
TODAY = date(2026, 5, 4)

FRESH = """# Changelog

Each PR adds one line under `[Unreleased]`.

## [Unreleased]

### Added

- The first route (#1).
"""

RELEASED_ONCE = """# Changelog

## [Unreleased]

### Fixed

- A date without its offset is refused (#7).

## [0.1.0] - 2026-04-01

### Added

- The first route (#1).
"""


class TestCut:
    def test_what_was_unreleased_becomes_the_version_under_an_empty_unreleased(self):
        cut = release.cut(RELEASED_ONCE, "0.2.0", current="0.1.0", today=TODAY)

        assert [heading for heading, _ in release.sections(cut)] == [
            "## [Unreleased]",
            "## [0.2.0] - 2026-05-04",
            "## [0.1.0] - 2026-04-01",
        ]
        assert release.notes(cut, "Unreleased") == ""
        assert release.notes(cut, "0.2.0") == (
            "### Fixed\n\n- A date without its offset is refused (#7)."
        )
        assert release.notes(cut, "0.1.0") == "### Added\n\n- The first route (#1)."

    def test_the_first_release_keeps_the_version_the_project_started_with(self):
        cut = release.cut(FRESH, "0.1.0", current="0.1.0", today=TODAY)

        assert release.notes(cut, "0.1.0") == "### Added\n\n- The first route (#1)."
        assert cut.startswith("# Changelog\n\nEach PR adds one line under `[Unreleased]`.\n")

    @pytest.mark.parametrize("version", ["1.2", "v1.2.3", "1.2.3rc1", "1.2.3.4", "01.2.3", ""])
    def test_a_version_that_is_not_three_numbers_is_refused(self, version: str):
        with pytest.raises(release.ReleaseError, match="not a version like"):
            release.cut(FRESH, version, current="0.1.0", today=TODAY)

    def test_a_version_lower_than_the_current_one_is_refused(self):
        with pytest.raises(release.ReleaseError, match="lower than the current version"):
            release.cut(RELEASED_ONCE, "0.0.9", current="0.1.0", today=TODAY)

    def test_versions_compare_as_numbers(self):
        # As text, "0.10.0" sorts before "0.9.0".
        changelog = RELEASED_ONCE.replace("0.1.0", "0.9.0")
        assert "## [0.10.0]" in release.cut(changelog, "0.10.0", current="0.9.0", today=TODAY)

    def test_a_version_that_has_its_section_is_refused(self):
        with pytest.raises(release.ReleaseError, match="already has its section"):
            release.cut(RELEASED_ONCE, "0.1.0", current="0.1.0", today=TODAY)

    def test_without_a_line_under_unreleased_there_is_nothing_to_release(self):
        empty = RELEASED_ONCE.replace("- A date without its offset is refused (#7).\n", "")
        with pytest.raises(release.ReleaseError, match="nothing to release"):
            release.cut(empty, "0.2.0", current="0.1.0", today=TODAY)

    def test_a_changelog_without_unreleased_is_refused(self):
        with pytest.raises(release.ReleaseError, match="no `## \\[Unreleased\\]` section"):
            release.cut("# Changelog\n\n- A line.\n", "0.1.0", current="0.1.0", today=TODAY)


class TestPending:
    """What the release workflow publishes: the current version, once it has its section."""

    def test_a_version_without_its_section_publishes_nothing(self):
        assert release.pending(FRESH, "0.1.0") is None
        assert release.pending(RELEASED_ONCE, "0.2.0") is None

    def test_a_version_with_its_section_is_the_one_to_publish(self):
        assert release.pending(RELEASED_ONCE, "0.1.0") == "0.1.0"

    def test_a_longer_version_is_not_taken_for_a_shorter_one(self):
        assert release.pending(RELEASED_ONCE.replace("0.1.0", "0.1.01"), "0.1.0") is None


def problems(changelog: str, version: str) -> list[str]:
    """What is wrong in a changelog for the version pyproject.toml declares."""
    headings = [heading for heading, _ in release.sections(changelog)]
    found: list[str] = []
    if headings[:1] != [release.UNRELEASED]:
        found.append("the first section is not `## [Unreleased]`")

    versions: list[str] = []
    for heading in headings[1:]:
        match = release.RELEASED.fullmatch(heading)
        if match is None:
            found.append(f"not `## [X.Y.Z] - YYYY-MM-DD`: {heading}")
        else:
            versions.append(match[1])

    order = [release.parse(v) for v in versions]
    if order != sorted(set(order), reverse=True):
        found.append(f"versions are not newest first, each once: {versions}")
    if versions and versions[0] != version:
        found.append(f"pyproject.toml says {version}, the newest section is {versions[0]}")
    return found


def test_scanner_sees_the_sections_of_the_changelog():
    # Canary: if the parser stops finding headings, the check below passes on an empty list.
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert release.sections(changelog)[0][0] == release.UNRELEASED


def test_changelog_and_pyproject_agree():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]

    assert problems(changelog, version) == [], "cut releases with scripts/release.py"


def test_detector_accepts_a_changelog_with_and_without_releases():
    assert problems(FRESH, "0.1.0") == []
    assert problems(RELEASED_ONCE, "0.1.0") == []


@pytest.mark.parametrize(
    ("changelog", "version", "problem"),
    [
        # The version raised in pyproject.toml alone, and a section written alone.
        (RELEASED_ONCE, "0.2.0", "pyproject.toml says 0.2.0"),
        (RELEASED_ONCE.replace("[0.1.0]", "[0.2.0]"), "0.1.0", "pyproject.toml says 0.1.0"),
        # Headings the release workflow would not find.
        (RELEASED_ONCE.replace("## [0.1.0] - 2026-04-01", "## [0.1.0]"), "0.1.0", "not `## ["),
        (RELEASED_ONCE.replace("## [0.1.0]", "## 0.1.0"), "0.1.0", "not `## ["),
        (RELEASED_ONCE.replace("## [0.1.0]", "## [v0.1.0]"), "0.1.0", "not `## ["),
        (RELEASED_ONCE.replace("## [Unreleased]", "## Unreleased"), "0.1.0", "first section"),
        (RELEASED_ONCE.replace("## [Unreleased]\n", ""), "0.1.0", "first section"),
        # A release added at the bottom, and the same one twice.
        (RELEASED_ONCE + "\n## [0.2.0] - 2026-05-04\n", "0.1.0", "newest first"),
        (RELEASED_ONCE + "\n## [0.1.0] - 2026-04-01\n", "0.1.0", "newest first"),
    ],
)
def test_detector_catches_a_changelog_that_left_the_version_behind(
    changelog: str, version: str, problem: str
):
    assert any(problem in found for found in problems(changelog, version)), problems(
        changelog, version
    )
