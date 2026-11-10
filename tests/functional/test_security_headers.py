from httpx import ASGITransport, AsyncClient

from app.core.security.headers import CSP, SecurityHeadersMiddleware


async def test_api_responses_carry_the_hardening_headers(client: AsyncClient):
    response = await client.get("/v1/health/liveness")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Content-Security-Policy"] == CSP
    assert "Strict-Transport-Security" not in response.headers  # HSTS off by default


async def test_docs_are_exempt_from_the_csp(client: AsyncClient):
    # Swagger UI loads scripts from a CDN: the API's CSP would leave it blank.
    response = await client.get("/docs")

    assert response.status_code == 200
    assert "Content-Security-Policy" not in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"


async def _plain_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


async def test_hsts_when_enabled():
    app = SecurityHeadersMiddleware(_plain_app, hsts=True, hsts_max_age=60)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as c:
        response = await c.get("/")
    assert response.headers["Strict-Transport-Security"] == "max-age=60; includeSubDomains"


async def test_exempt_paths_ignore_the_root_path():
    # Behind a proxy prefix, scope["path"] includes root_path; exempt paths do not.
    app = SecurityHeadersMiddleware(_plain_app, csp_exempt_paths=["/docs"])
    async with AsyncClient(
        transport=ASGITransport(app=app, root_path="/api"), base_url="http://test"
    ) as c:
        response = await c.get("/api/docs")
    assert "Content-Security-Policy" not in response.headers
