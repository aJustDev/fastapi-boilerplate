"""Figures for docs/architecture.md: python3 docs/img/architecture.py"""

from pathlib import Path

from _figures import guardar, steps


def request():
    return steps(
        "arch-f1",
        [
            {
                "title": "1 - Middleware",
                "sub": "metrics, request id, rate limit, CORS, gzip",
            },
            {
                "title": "2 - Router: app/<context>/api",
                "sub": "parses HTTP, resolves auth and repos via app.deps",
            },
            {
                "title": "3 - One use case per endpoint",
                "sub": "orders the steps, publishes events",
            },
            {
                "title": "4 - Service: the business rules",
                "sub": "reusable by several use cases",
                "branch": (
                    None,
                    "Plain CRUD has no service: the use case calls the repository.",
                    "note",
                ),
            },
            {"title": "5 - Repository", "sub": "queries through BaseRepo; flush, never commit"},
            {
                "title": "6 - get_session commits or rolls back",
                "sub": "the response is built from the schemas",
                "tone": "done",
            },
        ],
        note="Contexts never import each other: they share data by id and react to each other "
        "through events. app.core is infrastructure and imports no context.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("architecture-request", request),))
