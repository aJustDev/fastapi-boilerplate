from unittest.mock import AsyncMock

from app.core.logging.context import request_id_var
from app.core.logging.middleware import RequestIdMiddleware


class TestRequestIdMiddleware:
    async def test_generates_request_id_when_not_provided(self):
        captured_rid = None

        async def inner_app(scope, receive, send):
            nonlocal captured_rid
            captured_rid = request_id_var.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        mw = RequestIdMiddleware(inner_app)
        sent_messages = []

        async def mock_send(msg):
            sent_messages.append(msg)

        await mw({"type": "http", "headers": []}, AsyncMock(), mock_send)

        assert captured_rid
        assert len(captured_rid) == 32  # uuid4 hex
        start_msg = sent_messages[0]
        header_dict = dict(start_msg["headers"])
        assert b"x-request-id" in header_dict
        assert header_dict[b"x-request-id"] == captured_rid.encode()

    async def test_accepts_client_request_id(self):
        captured_rid = None

        async def inner_app(scope, receive, send):
            nonlocal captured_rid
            captured_rid = request_id_var.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = RequestIdMiddleware(inner_app)
        scope = {"type": "http", "headers": [(b"x-request-id", b"my-custom-id")]}
        await mw(scope, AsyncMock(), AsyncMock())

        assert captured_rid == "my-custom-id"

    async def test_context_is_reset_after_request(self):
        async def inner_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = RequestIdMiddleware(inner_app)
        await mw({"type": "http", "headers": []}, AsyncMock(), AsyncMock())

        assert request_id_var.get() == ""

    async def test_skips_non_http_scopes(self):
        inner = AsyncMock()
        mw = RequestIdMiddleware(inner)
        await mw({"type": "lifespan"}, AsyncMock(), AsyncMock())
        inner.assert_called_once()
