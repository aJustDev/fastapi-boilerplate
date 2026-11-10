from collections.abc import Iterable, Sequence

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class TrustedHostMiddleware:
    """Rejects requests whose Host header is not one of `allowed_hosts`.

    Like Starlette's middleware of the same name, with two differences:

    - `exempt_paths` are served whatever the Host. They are the probes: a container
      health check asks for `localhost`, an orchestrator for the address of the instance,
      and neither is a name the API answers to. A probe returns no data and builds no
      link, so the Host it arrives with cannot be abused.
    - the rejection is the JSON of the error contract (400, `invalid_host`), not text.

    A pattern is an exact host or `*.example.com` for any subdomain; `*` allows every host.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        allowed_hosts: Sequence[str],
        exempt_paths: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.allowed_hosts = [host.lower() for host in allowed_hosts]
        self.allow_any = "*" in self.allowed_hosts
        self.exempt_paths = frozenset(exempt_paths)

    @staticmethod
    def _hostname(header: str) -> str:
        """The Host header without its port; an IPv6 literal keeps its brackets."""
        if header.startswith("["):
            return header.split("]")[0] + "]"
        return header.split(":")[0]

    def _is_allowed(self, host: str) -> bool:
        return any(
            host == pattern or (pattern.startswith("*.") and host.endswith(pattern[1:]))
            for pattern in self.allowed_hosts
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] not in ("http", "websocket")
            or self.allow_any
            or scope.get("path") in self.exempt_paths
        ):
            await self.app(scope, receive, send)
            return

        host = self._hostname(Headers(scope=scope).get("host", "").lower())
        if self._is_allowed(host):
            await self.app(scope, receive, send)
            return

        response = JSONResponse(
            status_code=400, content={"detail": "Invalid host header", "code": "invalid_host"}
        )
        await response(scope, receive, send)
