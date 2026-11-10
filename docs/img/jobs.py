"""Figures for docs/jobs.md: python3 docs/img/jobs.py"""

from pathlib import Path

from _figures import guardar, steps


def cycle():
    return steps(
        "jobs-f1",
        [
            {
                "title": "1 - Every poll, each worker lists due jobs",
                "sub": "a plain SELECT of ids, no locks held",
                "branch": (
                    None,
                    "First it frees RUNNING jobs whose lease expired: their worker died.",
                    "note",
                ),
            },
            {
                "title": "2 - Did this worker win the claim?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "Another worker moved it to RUNNING first: skip it.", "bad"),
            },
            {
                "title": "3 - Run the handler, with a timeout",
                "sub": "no transaction open while it runs",
                "branch": (
                    None,
                    "If the worker dies here, the lease runs out and another worker frees the job.",
                    "note",
                ),
            },
            {
                "title": "4 - Reschedule in one UPDATE",
                "sub": "PENDING, next run = now + interval, lease cleared",
                "tone": "done",
            },
        ],
        note="The claim is a conditional UPDATE from PENDING to RUNNING that also sets the lease: "
        "PostgreSQL lets exactly one worker change the row.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("jobs-cycle", cycle),))
