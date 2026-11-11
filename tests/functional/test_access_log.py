"""The access line: one per request, written by the app, without the query string."""

import logging
import re
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from app.core.logging.middleware import AccessLogMiddleware

LINE = re.compile(
    r"^(?P<method>[A-Z]+) (?P<path>\S+) (?P<outcome>\d{3}(?: [a-z_]+)?) (?P<ms>\d+(?:\.\d)?)ms$"
)
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _access_lines(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "app.access"]


def _line(record: logging.LogRecord) -> re.Match[str]:
    """The parts of an access line; the suite runs as `local`, where it may be colored."""
    match = LINE.match(ANSI.sub("", record.getMessage()))
    assert match is not None, record.getMessage()
    return match


@pytest.fixture
def signed_in(fake_user):
    with (
        patch("app.auth.repos.revoked_token.RevokedTokenRepo.is_revoked", return_value=False),
        patch("app.auth.repos.user.UserRepo.get_by_id", return_value=fake_user),
    ):
        yield


async def test_a_request_leaves_one_line_with_its_outcome(client: AsyncClient, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/v1/does-not-exist")

    [record] = _access_lines(caplog)
    line = _line(record)
    assert line["method"] == "GET"
    assert line["path"] == "/v1/does-not-exist"
    assert line["outcome"] == "404 not_found"
    http = record.fields["http"]
    assert (http["status"], http["error"], http["path"]) == (404, "not_found", "/v1/does-not-exist")
    assert http["duration_ms"] >= 0


async def test_a_success_has_no_error_code(client: AsyncClient, auth_headers, signed_in, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/v1/auth/me", headers=auth_headers)

    [record] = _access_lines(caplog)
    assert _line(record)["outcome"] == "200"
    assert record.fields["http"]["error"] is None


async def test_the_code_of_a_domain_error(client: AsyncClient, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/v1/auth/me")

    [record] = _access_lines(caplog)
    assert _line(record)["outcome"] == "401 unauthenticated"


async def test_an_unhandled_error_has_its_line(
    client: AsyncClient, auth_headers, signed_in, caplog
):
    with (
        patch("app.workshops.repos.workshop.WorkshopRepo.get_by_id", side_effect=RuntimeError),
        caplog.at_level(logging.INFO, logger="app.access"),
    ):
        await client.get("/v1/workshops/1", headers=auth_headers)

    [record] = _access_lines(caplog)
    assert _line(record)["outcome"] == "500 internal_error"


async def test_the_query_string_is_not_logged(client: AsyncClient, caplog):
    # The client writes it: search terms, emails, a token pasted into a link.
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/v1/does-not-exist?email=someone@example.com")

    [record] = _access_lines(caplog)
    assert "someone" not in record.getMessage()
    assert "someone" not in str(record.fields)


async def test_an_encoded_newline_cannot_start_a_line(client: AsyncClient, caplog):
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.get("/v1/a%0AINFO: forged")

    [record] = _access_lines(caplog)
    assert "\n" not in record.getMessage()
    assert "/v1/a%0AINFO:%20forged" in record.getMessage()


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/v1/health/liveness"),
        ("GET", "/v1/health/readiness"),
        ("GET", "/v1/metrics"),
        ("OPTIONS", "/v1/workshops"),
    ],
)
async def test_probes_scrapes_and_preflights_leave_no_line(
    client: AsyncClient, caplog, method: str, path: str
):
    headers = {"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    with caplog.at_level(logging.INFO, logger="app.access"):
        await client.request(method, path, headers=headers)

    assert _access_lines(caplog) == []


async def test_on_a_color_terminal_the_outcome_is_colored(caplog, monkeypatch):
    async def teapot(scope, receive, send):
        await send({"type": "http.response.start", "status": 418, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    monkeypatch.setattr("app.core.logging.middleware.ansi_enabled", lambda: True)
    scope = {"type": "http", "method": "GET", "path": "/x", "raw_path": b"/x", "headers": []}

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        pass

    with caplog.at_level(logging.INFO, logger="app.access"):
        await AccessLogMiddleware(teapot)(scope, receive, send)

    [record] = _access_lines(caplog)
    assert record.getMessage().startswith("GET /x \033[33m418\033[0m ")


@pytest.mark.parametrize(
    ("seconds", "shown"), [(0.0004, "0.4ms"), (0.0099, "9.9ms"), (0.0123, "12ms")]
)
def test_a_fast_request_is_not_0ms(caplog, seconds: float, shown: str):
    scope = {"type": "http", "method": "GET", "path": "/x", "raw_path": b"/x"}
    middleware = AccessLogMiddleware(None)
    middleware._color = False

    with caplog.at_level(logging.INFO, logger="app.access"):
        middleware._log(scope, 200, None, seconds)

    [record] = _access_lines(caplog)
    assert record.getMessage() == f"GET /x 200 {shown}"
