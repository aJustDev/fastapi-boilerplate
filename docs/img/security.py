"""Figures for docs/security.md: python3 docs/img/security.py"""

from pathlib import Path

from _figures import guardar, steps


def stack():
    return steps(
        "sec-f1",
        [
            {
                "title": "1 - ProxyHeaders, request id, access line",
                "sub": "real client IP; an id and a log line per response",
            },
            {
                "title": "2 - TrustedHost: allowed Host?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "400 before any work is done. Health probes are exempt.", "bad"),
            },
            {
                "title": "3 - Metrics, security headers, CORS",
                "sub": "security headers are added on the way out",
            },
            {
                "title": "4 - Dependencies: valid token?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "401, unless the route is public.", "bad"),
            },
            {
                "title": "5 - Dependencies: route permission?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "403: the user may not do this kind of thing.", "bad"),
            },
            {
                "title": "6 - Endpoint limit: under it?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "429 with Retry-After in seconds.", "bad"),
            },
            {
                "title": "7 - The use case: is the resource the user's?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "404, the same answer as an id that does not exist.", "bad"),
            },
            {"title": "8 - The use case does its work", "sub": "and commits", "tone": "done"},
        ],
        note="The proxy step comes first so the rate limit and the logs see the real client "
        "address. The limit is a decorator of each endpoint, so it is checked after the "
        "dependencies. A holder of the manage permission of a context skips step 7.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("security-stack", stack),))
