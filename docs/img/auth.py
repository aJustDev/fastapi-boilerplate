"""Figures for docs/auth.md: python3 docs/img/auth.py"""

from pathlib import Path

from _figures import guardar, steps


def tokens():
    return steps(
        "auth-f1",
        [
            {
                "title": "1 - Login with email or username",
                "sub": "argon2 runs in the thread pool, not on the event loop",
            },
            {
                "title": "2 - Account exists and password matches?",
                "tone": "decision",
                "down": "yes",
                "branch": (
                    "no",
                    "401. An unknown account also pays a full password check against a dummy hash.",
                    "bad",
                ),
            },
            {
                "title": "3 - Access and refresh tokens issued",
                "sub": "access for 30 min, refresh for 7 days",
            },
            {
                "title": "4 - Refresh: is this refresh token unused?",
                "tone": "decision",
                "down": "yes",
                "branch": (
                    "no",
                    "Replay: every session of the account ends, then 401. The user logs in again.",
                    "bad",
                ),
            },
            {
                "title": "5 - The used refresh token is revoked",
                "sub": "and a new pair is issued",
            },
            {
                "title": "6 - Logout revokes both tokens",
                "sub": "the access token, and the refresh token if sent",
                "tone": "done",
            },
        ],
        note="Every authenticated request checks the access token: signature and expiry, not "
        "revoked, user active, and issued for the current session version of the account.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("auth-tokens", tokens),))
