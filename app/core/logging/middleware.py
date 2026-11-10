import re
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging.context import request_id_var

# The id goes verbatim into every log line of the request and into the response: anything
# outside this shape (spaces, brackets, control or non-ASCII bytes, kilobytes of text)
# could forge log content or break the request, so it is replaced, not rejected.
_CLIENT_ID = re.compile(rb"[A-Za-z0-9._-]{1,64}")


class RequestIdMiddleware:
    """ASGI middleware that assigns a unique request ID to each HTTP request.

    Accepts X-Request-ID from the client when it is a plain token of at most 64 characters
    (letters, digits, `.`, `_`, `-`); otherwise generates a UUID4.
    Sets the ContextVar so all downstream logging includes the request ID.
    Returns the X-Request-ID header in the response.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        client_id = headers.get(b"x-request-id", b"")
        rid = client_id.decode("ascii") if _CLIENT_ID.fullmatch(client_id) else uuid.uuid4().hex

        token = request_id_var.set(rid)
        try:

            async def send_with_request_id(message: Message) -> None:
                if message["type"] == "http.response.start":
                    response_headers = list(message.get("headers", []))
                    response_headers.append((b"x-request-id", rid.encode()))
                    message["headers"] = response_headers
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            request_id_var.reset(token)
