import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging.context import request_id_var


class RequestIdMiddleware:
    """ASGI middleware that assigns a unique request ID to each HTTP request.

    Accepts X-Request-ID from the client if provided, otherwise generates a UUID4.
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
        client_id = headers.get(b"x-request-id", b"").decode()
        rid = client_id or uuid.uuid4().hex

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
