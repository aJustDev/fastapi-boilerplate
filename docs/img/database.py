"""Figures for docs/database.md: python3 docs/img/database.py"""

from pathlib import Path

from _figures import guardar, steps


def session():
    return steps(
        "db-f1",
        [
            {
                "title": "1 - A request asks for a repository",
                "sub": "get_session opens one session for the request",
            },
            {
                "title": "2 - Use cases and repos change data",
                "sub": "repos flush, they never commit",
            },
            {
                "title": "3 - Did the endpoint raise?",
                "tone": "decision",
                "down": "no",
                "branch": (
                    "yes",
                    "Rollback: nothing of this request is stored, published events included.",
                    "bad",
                ),
            },
            {
                "title": "4 - Commit",
                "sub": "every change and event of the request, or none",
                "tone": "done",
            },
        ],
        note="Work that must survive a failed request (ending sessions after a stolen refresh "
        "token) opens its own session with async_session_factory and commits it.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("database-session", session),))
