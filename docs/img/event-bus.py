"""Figures for docs/event-bus.md: python3 docs/img/event-bus.py"""

from pathlib import Path

from _figures import guardar, steps


def dispatch():
    return steps(
        "eb-f1",
        [
            {
                "title": "1 - A use case publishes the event",
                "sub": "same transaction as the business change",
            },
            {
                "title": "2 - The request transaction commits",
                "sub": "PostgreSQL sends a NOTIFY to the workers",
                "branch": (
                    None,
                    "If the NOTIFY is lost, the periodic poll finds the event (30 s by default).",
                    "note",
                ),
            },
            {
                "title": "3 - A worker locks one pending event",
                "sub": "SKIP LOCKED: other workers take the next one",
            },
            {
                "title": "4 - Any handler for this event type?",
                "tone": "decision",
                "down": "yes",
                "branch": (
                    "no",
                    "Critical log and retry; it ends as failed and can be replayed.",
                    "bad",
                ),
            },
            {
                "title": "5 - Did every handler succeed?",
                "tone": "decision",
                "down": "yes",
                "branch": (
                    "no",
                    "Retry with backoff; handlers that already succeeded are skipped.",
                    "bad",
                ),
            },
            {
                "title": "6 - Marked as processed and committed",
                "sub": "the lock on the event ends with this commit",
                "tone": "done",
            },
        ],
        note="Each event is handled and committed in its own transaction, so no other worker can "
        "take it while it is being dispatched.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("event-bus-dispatch", dispatch),))
