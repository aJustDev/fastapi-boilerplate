"""Figures for docs/migrations.md: python3 docs/img/migrations.py"""

from pathlib import Path

from _figures import guardar, scenarios, steps


def startup():
    return steps(
        "mig-f1",
        [
            {"title": "1 - The database is up", "sub": "compose waits for pg_isready"},
            {
                "title": "2 - migrate runs alembic upgrade head",
                "sub": "one process, then it exits",
            },
            {
                "title": "3 - Did every migration apply?",
                "tone": "decision",
                "down": "yes",
                "branch": (
                    "no",
                    "The API does not start; the previous version keeps serving.",
                    "bad",
                ),
            },
            {
                "title": "4 - The API starts",
                "sub": "workers and jobs on the new schema",
                "tone": "done",
            },
        ],
        note="Migrations never run in the app lifespan: with several workers or replicas they "
        "would race to apply the same revision.",
    )


def safe_changes():
    return scenarios(
        "mig-f2",
        [
            (
                "Rename a column",
                "the old code is still running",
                "One migration renames it: the running version fails until the deploy ends.",
                "Add the new column, write both, backfill, read the new one, drop the old one later.",
            ),
            (
                "Index a big table",
                "writes keep coming",
                "CREATE INDEX blocks every write until the index is built.",
                "Build it CONCURRENTLY, outside the migration transaction.",
            ),
            (
                "Add a foreign key or CHECK",
                "on a table with data",
                "Validating every row holds a lock that blocks writes for the whole scan.",
                "Add it NOT VALID, then VALIDATE in a later step with a weaker lock.",
            ),
        ],
        before="Unsafe",
        now="Safe",
    )


if __name__ == "__main__":
    guardar(
        Path(__file__).parent,
        (("migrations-startup", startup), ("migrations-safe-changes", safe_changes)),
    )
