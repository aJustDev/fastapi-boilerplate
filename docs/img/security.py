"""Figures for docs/security.md: python3 docs/img/security.py"""

from pathlib import Path

from _figures import guardar, steps


def stack():
    return steps(
        "sec-f1",
        [
            {
                "title": "1 - ProxyHeaders",
                "sub": "client IP and scheme from trusted proxies only",
            },
            {
                "title": "2 - TrustedHost: allowed Host?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "400 before any work is done.", "bad"),
            },
            {
                "title": "3 - Metrics, request id, headers, CORS",
                "sub": "security headers are added on the way out",
            },
            {
                "title": "4 - Dependencies: valid token?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "401, unless the route is public.", "bad"),
            },
            {
                "title": "5 - Endpoint limit: under it?",
                "tone": "decision",
                "down": "yes",
                "branch": ("no", "429 with Retry-After in seconds.", "bad"),
            },
            {"title": "6 - The endpoint runs", "sub": "one use case", "tone": "done"},
        ],
        note="The proxy step comes first so the rate limit and the logs see the real client "
        "address. The limit is a decorator of each endpoint, so it is checked after the "
        "dependencies.",
    )


if __name__ == "__main__":
    guardar(Path(__file__).parent, (("security-stack", stack),))
