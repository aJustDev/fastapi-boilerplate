"""Figures for docs/auth.md: python3 docs/img/auth.py"""

from pathlib import Path

from _figures import guardar, scenarios, steps


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
                    "Replay: every token of the user issued until now is rejected, then 401.",
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
        "revoked, user active, and issued after the last invalidation of the account.",
    )


def risks():
    return scenarios(
        "auth-f2",
        [
            (
                "A refresh token is stolen",
                "a leaked log, a compromised device",
                "Thief and user could both refresh for 7 days; nothing noticed the second copy.",
                "Its first use rotates it; when the other copy comes back, every session of the "
                "user ends.",
            ),
            (
                "The user logs out",
                "explicit logout",
                "Only the access token was revoked: the refresh token kept opening new sessions.",
                "The refresh token sent with the logout is revoked too.",
            ),
            (
                "Login with an unknown account",
                "probing which emails exist",
                "It answered faster than a wrong password, so timing revealed which accounts exist.",
                "It runs the same password check against a dummy hash: both answers take as long.",
            ),
            (
                "Email in another case",
                "Foo@x.com and foo@x.com",
                "Login failed, and registering it again crashed with a 500.",
                "Lookups ignore case like the unique index; a duplicate registration is a 409.",
            ),
        ],
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("auth-tokens", tokens), ("auth-risks", risks)))
