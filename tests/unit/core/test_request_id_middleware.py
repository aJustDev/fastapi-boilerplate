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


class TestClientRequestIdIsValidated:
    @staticmethod
    async def _rid_for(header: bytes) -> str:
        captured = ""

        async def inner_app(scope, receive, send):
            nonlocal captured
            captured = request_id_var.get()
            await send({"type": "http.response.start", "status": 200, "headers": []})

        mw = RequestIdMiddleware(inner_app)
        await mw({"type": "http", "headers": [(b"x-request-id", header)]}, AsyncMock(), AsyncMock())
        return captured

    async def test_text_that_could_forge_a_log_line_is_replaced(self):
        rid = await self._rid_for(b"] FAKE > admin logged in from 10.0.0.1 [")
        assert len(rid) == 32

    async def test_bytes_that_are_not_text_do_not_break_the_request(self):
        rid = await self._rid_for(b"\xff\xfe")
        assert len(rid) == 32

    async def test_an_oversized_id_is_replaced(self):
        rid = await self._rid_for(b"a" * 65)
        assert len(rid) == 32

    async def test_ids_of_the_usual_shapes_are_kept(self):
        for value in (b"my-custom-id", b"0af7651916cd43dd8448eb211c80319c", b"req_1.2-3"):
            assert await self._rid_for(value) == value.decode()
