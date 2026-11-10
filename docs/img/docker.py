"""Figures for docs/docker.md: python3 docs/img/docker.py"""

from pathlib import Path

from _figures import guardar, scenarios


def image():
    return scenarios(
        "docker-f1",
        [
            (
                "Secrets in the build context",
                ".env.local next to the code",
                "COPY . . plus !.env.local in .dockerignore put the developer's secrets in "
                "the image.",
                "Only main.py and app/ are copied, and no .env file enters the build context.",
            ),
            (
                "A new file in the repo",
                "tests, notes, scripts",
                "It entered the image unless someone remembered to exclude it.",
                "It stays out unless it is added to the COPY list, which a test checks.",
            ),
            (
                "The app reports its version",
                "APP_VERSION",
                "Written twice, in pyproject.toml and config.py, free to drift apart.",
                "Read from the installed package: pyproject.toml is the only place to bump it.",
            ),
            (
                "Clock and tooling at runtime",
                "time zone, package manager",
                "TZ=Europe/Madrid and pip shipped in the image.",
                "UTC, like CI; no pip, nothing gets installed at runtime.",
            ),
        ],
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("docker-image", image),))
