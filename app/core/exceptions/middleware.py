import logging

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions.handlers import describe_unhandled, internal_error_response
from app.core.logging.middleware import record_error_code

logger = logging.getLogger(__name__)


class UnhandledErrorMiddleware:
    """Turns an exception nobody handled into the JSON 500 of the error contract.

    It is the innermost middleware on purpose. Starlette runs the handler registered for
    `Exception` in its ServerErrorMiddleware, outside every other middleware: a 500 built
    there has no CORS headers (a browser cannot read it), no security headers and no
    request id, in the response or in the log. Built here, it is a response like any
    other and travels back through the whole stack.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            if started:
                # Headers are already on the wire: no second response is possible, the
                # server closes the connection and logs the error.
                raise
            logger.exception(describe_unhandled(Request(scope), exc))
            record_error_code(scope, "internal_error")
            await internal_error_response()(scope, receive, send)
