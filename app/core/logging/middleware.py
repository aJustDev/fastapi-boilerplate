import logging
import re
import time
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging.config import ansi_enabled
from app.core.logging.context import actor_var, request_id_var

LIVENESS_PATH = "/v1/health/liveness"
READINESS_PATH = "/v1/health/readiness"
METRICS_PATH = "/v1/metrics"
# Not traffic: an orchestrator's probes and Prometheus' scrapes, every few seconds per
# instance, would outnumber the requests worth reading. CORS preflights are left out too.
QUIET_PATHS = frozenset({LIVENESS_PATH, READINESS_PATH, METRICS_PATH})

access_logger = logging.getLogger("app.access")

_ERROR_CODE = "error_code"
# SGR color of a status on a color terminal, by its first digit.
_STATUS_COLORS = {"2": "32", "3": "36", "4": "33", "5": "31"}

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
        # A request starts as nobody: whoever authenticates sets it (get_current_user).
        actor_token = actor_var.set(None)
        try:

            async def send_with_request_id(message: Message) -> None:
                if message["type"] == "http.response.start":
                    response_headers = list(message.get("headers", []))
                    response_headers.append((b"x-request-id", rid.encode()))
                    message["headers"] = response_headers
                await send(message)

            await self.app(scope, receive, send_with_request_id)
        finally:
            actor_var.reset(actor_token)
            request_id_var.reset(token)


def record_error_code(scope: Scope, code: str) -> None:
    """Name the error of the response, for its access line (the `code` of the body)."""
    scope.setdefault("state", {})[_ERROR_CODE] = code


class AccessLogMiddleware:
    """One line per request, once its response is sent.

    `GET /v1/workshops/7 404 not_found 3ms`: method, path, status, the error code when
    there is one, and the time to answer. In JSON the same facts are fields of `http`, with
    the client address. The path goes without its query string: the client writes it, and
    it can carry search terms, emails or tokens. Uvicorn's own access log is off
    (`setup_logging`): it had neither the time nor the error code, and it copied the query.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._color = ansi_enabled()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or scope["path"] in QUIET_PATHS:
            await self.app(scope, receive, send)
            return

        # Created here, so the handlers write the error code where this layer reads it even
        # if a layer between them copies the scope.
        state = scope.setdefault("state", {})
        status = 500  # if no response starts, the server answers 500
        start = time.perf_counter()

        async def send_with_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            self._log(scope, status, state.get(_ERROR_CODE), time.perf_counter() - start)

    def _log(self, scope: Scope, status: int, code: str | None, seconds: float) -> None:
        # The raw path: still percent-encoded, so a %0A in the URL cannot start a new line
        # in a text log.
        raw = scope.get("raw_path")
        path = raw.decode("ascii", "backslashreplace") if raw else scope["path"]
        client = scope.get("client")
        outcome = f"{status} {code}" if code else str(status)
        if self._color:
            outcome = f"\033[{_STATUS_COLORS.get(str(status)[0], '0')}m{outcome}\033[0m"
        milliseconds = seconds * 1000
        # Tenths below 10 ms, where most requests of an idle local server fall and a 0
        # would say nothing; whole milliseconds above.
        duration = f"{milliseconds:.1f}ms" if milliseconds < 10 else f"{milliseconds:.0f}ms"
        access_logger.info(
            "%s %s %s %s",
            scope["method"],
            path,
            outcome,
            duration,
            extra={
                "fields": {
                    "http": {
                        "method": scope["method"],
                        "path": path,
                        "status": status,
                        "error": code,
                        "duration_ms": round(milliseconds, 1),
                        "client": client[0] if client else None,
                    }
                }
            },
        )
