import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security.trusted_host import TrustedHostMiddleware


async def _ok(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def _client(allowed: list[str], exempt: tuple[str, ...] = ()) -> AsyncClient:
    app = TrustedHostMiddleware(_ok, allowed_hosts=allowed, exempt_paths=exempt)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _status(client: AsyncClient, host: str, path: str = "/v1/items") -> int:
    async with client:
        return (await client.get(path, headers={"Host": host})).status_code


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("api.example.com", 200),
        ("API.Example.COM", 200),
        ("api.example.com:8443", 200),
        ("evil.example.org", 400),
        ("api.example.com.evil.org", 400),
        ("localhost", 400),
        ("", 400),
    ],
)
async def test_only_the_listed_host_is_served(host: str, expected: int):
    assert await _status(_client(["api.example.com"]), host) == expected


async def test_a_wildcard_pattern_covers_subdomains_only():
    allowed = ["*.example.com"]
    assert await _status(_client(allowed), "a.example.com") == 200
    assert await _status(_client(allowed), "a.b.example.com") == 200
    assert await _status(_client(allowed), "example.com") == 400
    assert await _status(_client(allowed), "badexample.com") == 400


async def test_an_ipv6_literal_is_matched_with_its_brackets():
    assert await _status(_client(["[::1]"]), "[::1]:8000") == 200
    assert await _status(_client(["[::1]"]), "[::2]:8000") == 400


async def test_star_allows_every_host():
    assert await _status(_client(["*"]), "anything.example") == 200


async def test_probes_are_served_whatever_the_host():
    # The image's HEALTHCHECK asks for localhost, an orchestrator for the instance address.
    client = _client(["api.example.com"], exempt=("/v1/health/liveness",))
    assert await _status(client, "localhost:8000", "/v1/health/liveness") == 200
    client = _client(["api.example.com"], exempt=("/v1/health/liveness",))
    assert await _status(client, "10.0.3.7", "/v1/health/liveness") == 200
    client = _client(["api.example.com"], exempt=("/v1/health/liveness",))
    assert await _status(client, "localhost:8000", "/v1/health/liveness/x") == 400


async def test_the_rejection_follows_the_error_contract():
    async with _client(["api.example.com"]) as client:
        response = await client.get("/v1/items", headers={"Host": "evil.example.org"})

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid host header", "code": "invalid_host"}
