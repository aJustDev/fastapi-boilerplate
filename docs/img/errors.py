"""Figures for docs/errors.md: python3 docs/img/errors.py"""

from pathlib import Path

from _figures import guardar, scenarios


def responses():
    return scenarios(
        "err-f1",
        [
            (
                "Two requests insert the same row",
                "a race past the service check",
                "The IntegrityError reached the catch-all: 500 and an alert for a duplicate.",
                "409 with code integrity_conflict: the client can retry or show a message.",
            ),
            (
                "A route that does not exist",
                "typo, old client",
                "FastAPI's own body without a code, unlike every other error.",
                "404 with code not_found, the same as a missing resource.",
            ),
            (
                "Too many requests",
                "a limit is hit",
                "Retry-After held the word 'minute' instead of a number.",
                "429, code rate_limited, Retry-After in seconds until the window opens.",
            ),
            (
                "Any error, in OpenAPI",
                "generated clients",
                "The schema showed FastAPI's validation error, not what the API sent.",
                "ErrorResponse and ValidationErrorResponse, checked by a test.",
            ),
        ],
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("errors-responses", responses),))
