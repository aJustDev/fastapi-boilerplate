"""Every API route answers 401 without credentials, unless it is listed as public.

It runs real requests on purpose: declaring an auth dependency and having it run are
two different things, and only the request tells them apart.

If it fails:
- the endpoint should require credentials: it lacks `CurrentUser` (app/deps/auth.py);
- the endpoint is public on purpose: add it to PUBLIC with the reason. The list is the
  anonymous surface of the API, so every entry should be a visible decision in the diff.
"""

import re

import pytest
from httpx import AsyncClient

from tests._routes import iter_api_routes

# Routes that answer without credentials, one by one (no prefixes), with the reason.
PUBLIC: dict[str, str] = {
    "/v1/health/liveness": "orchestrator probe, no data",
    "/v1/health/readiness": "orchestrator probe, no data",
    "/v1/metrics": "Prometheus scrape; keep it off the public network",
    "/v1/auth/login": "issues the tokens",
    "/v1/auth/register": "creates the account",
    "/v1/auth/refresh": "the refresh token in the body is the credential",
}

_PARAM = re.compile(r"\{([^}:]+)(?::[^}]+)?\}")


def _url(path: str) -> str:
    # A well-formed value: a malformed one would give 422 before the auth check.
    return _PARAM.sub("1", path)


def _protected() -> list[tuple[str, str]]:
    found = set()
    for ctx in iter_api_routes():
        if ctx.path in PUBLIC:
            continue
        for method in ctx.route.methods - {"HEAD", "OPTIONS"}:
            found.add((method, ctx.path))
    return sorted(found)


def test_scanner_sees_the_api():
    # Canary: if FastAPI changes how it exposes routes and the scanner sees none, the
    # parametrized test below would pass on zero cases.
    assert len(_protected()) >= 8


def test_public_has_no_stale_entries():
    # A dead entry is a pre-granted exemption: the day a route appears there, it is born
    # anonymous without anyone deciding it.
    live = {ctx.path for ctx in iter_api_routes()}
    assert not set(PUBLIC) - live, f"PUBLIC lists routes that do not exist: {set(PUBLIC) - live}"


@pytest.mark.parametrize(("method", "path"), _protected())
async def test_endpoint_requires_credentials(client: AsyncClient, method: str, path: str):
    response = await client.request(method, _url(path))
    assert response.status_code == 401, (
        f"{method} {path} answers {response.status_code} without credentials: it lacks the "
        "auth dependency, or it is public on purpose and belongs in PUBLIC."
    )
