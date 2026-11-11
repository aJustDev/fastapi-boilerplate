"""Cut a release: the version in pyproject.toml and its section in CHANGELOG.md.

Usage, from the repository root:

    uv run python scripts/release.py cut 0.2.0    # writes pyproject.toml, uv.lock, CHANGELOG.md
    uv run python scripts/release.py pending      # the version waiting to be published, if any
    uv run python scripts/release.py notes 0.2.0  # what CHANGELOG.md says of that version

`cut` touches no git state: its three files go in a PR, and the release workflow publishes
what `pending` prints once that PR is merged (docs/releases.md).
"""

import argparse
import re
import subprocess
import sys
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

CHANGELOG = Path("CHANGELOG.md")
PYPROJECT = Path("pyproject.toml")

UNRELEASED = "## [Unreleased]"
# The heading of a released version, the only other `## ` heading the file may have.
RELEASED = re.compile(r"## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}")

_VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_UNRELEASED_LINE = re.compile(r"^## \[Unreleased\][ \t]*$", re.MULTILINE)


class ReleaseError(Exception):
    """Why there is no release to cut or to show; printed as it is."""


def parse(version: str) -> tuple[int, ...]:
    if not _VERSION.fullmatch(version):
        raise ReleaseError(f"{version!r} is not a version like 1.2.3")
    return tuple(int(part) for part in version.split("."))


def sections(changelog: str) -> list[tuple[str, str]]:
    """Each `## ` heading with the text under it, in the order of the file."""
    found: list[tuple[str, list[str]]] = []
    for line in changelog.splitlines():
        if line.startswith("## "):
            found.append((line.rstrip(), []))
        elif found:
            found[-1][1].append(line)
    return [(heading, "\n".join(body).strip()) for heading, body in found]


def notes(changelog: str, name: str) -> str | None:
    """The text under `## [name]`; None when the file has no such section."""
    for heading, body in sections(changelog):
        if heading.startswith(f"## [{name}]"):
            return body
    return None


def pending(changelog: str, current: str) -> str | None:
    """The current version once it has its section: the one the release workflow publishes.

    A version without a section is still being worked on, and publishes nothing.
    """
    return current if notes(changelog, current) is not None else None


def cut(changelog: str, version: str, *, current: str, today: date) -> str:
    """The changelog with what was under [Unreleased] moved under `version`."""
    if parse(version) < parse(current):
        raise ReleaseError(f"{version} is lower than the current version, {current}")
    if notes(changelog, version) is not None:
        raise ReleaseError(f"{version} already has its section in {CHANGELOG}")
    unreleased = notes(changelog, "Unreleased")
    if unreleased is None or not _UNRELEASED_LINE.search(changelog):
        raise ReleaseError(f"{CHANGELOG} has no `{UNRELEASED}` section")
    if not any(line.startswith("- ") for line in unreleased.splitlines()):
        raise ReleaseError("nothing under [Unreleased]: there is nothing to release")
    heading = f"{UNRELEASED}\n\n## [{version}] - {today.isoformat()}"
    return _UNRELEASED_LINE.sub(lambda _: heading, changelog, count=1)


def _read() -> tuple[str, str]:
    try:
        current = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["version"]
        return CHANGELOG.read_text(encoding="utf-8"), current
    except FileNotFoundError as e:
        raise ReleaseError(f"{e.filename} not found: run it from the repository root") from e


def _cut(version: str) -> None:
    changelog, current = _read()
    cut_changelog = cut(changelog, version, current=current, today=datetime.now(UTC).date())
    # The first release of a project keeps the version it started with: only the changelog
    # changes. Any other goes through uv, which writes pyproject.toml and uv.lock together.
    # The argument is a version that parse() accepted.
    written = f"{CHANGELOG}"
    if version != current:
        bump = subprocess.run(["uv", "version", version], check=False)  # noqa: S603, S607
        if bump.returncode != 0:
            raise ReleaseError(f"`uv version` failed; {CHANGELOG} was not touched")
        written = f"{PYPROJECT}, uv.lock and {CHANGELOG}"
    CHANGELOG.write_text(cut_changelog, encoding="utf-8")
    print(
        f"{version} is cut. Commit {written} as `chore(release): {version}`; "
        "merging that PR publishes it."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Cut a release (docs/releases.md).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("cut", help="set the version and give it what is under [Unreleased]")
    commands.choices["cut"].add_argument("version", help="like 1.2.3")
    commands.add_parser("pending", help="print the current version if it has its section")
    commands.add_parser("notes", help="print the section of a version")
    commands.choices["notes"].add_argument("version", help="like 1.2.3")
    args = parser.parse_args()

    try:
        if args.command == "cut":
            _cut(args.version)
        elif args.command == "pending":
            version = pending(*_read())
            if version:
                print(version)
        else:
            section = notes(_read()[0], args.version)
            if section is None:
                raise ReleaseError(f"{args.version} has no section in {CHANGELOG}")
            print(section)
    except ReleaseError as e:
        sys.exit(f"release: {e}")


if __name__ == "__main__":
    main()
