"""Figures for docs/workshops.md: python3 docs/img/workshops.py"""

from pathlib import Path

from _figures import guardar, steps


def enroll():
    return steps(
        "workshops-f1",
        [
            {
                "title": "1 - Lock the workshop row",
                "sub": "SELECT ... FOR UPDATE, until the commit",
                "branch": (
                    None,
                    "Another request about this workshop waits here. Requests about other "
                    "workshops are not held up.",
                    "note",
                ),
            },
            {
                "title": "2 - Is this user already enrolled?",
                "tone": "decision",
                "down": "no",
                "branch": ("yes", "Answer 200 with the enrollment that exists.", "done"),
            },
            {
                "title": "3 - Is a seat free?",
                "tone": "decision",
                "down": "yes",
                "branch": (
                    "no",
                    "Store it as waitlisted, last in line. No event.",
                    "note",
                ),
            },
            {
                "title": "4 - Store it as confirmed, count the seat",
                "sub": "and the enrollment.confirmed event, in the same commit",
                "tone": "done",
            },
        ],
        note="Leaving takes the same lock: the enrollment is cancelled and, if it held a seat, "
        "the first person waiting is confirmed before anyone else can enrol.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("workshops-enroll", enroll),))
