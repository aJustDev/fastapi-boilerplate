from collections.abc import Iterable

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# A JSON API loads nothing and is embedded nowhere: everything 'none'. `frame-ancestors`
# is the modern X-Frame-Options, which stays for older clients.
CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
PERMISSIONS_POLICY = (
    "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), payment=(), usb=()"
)


class SecurityHeadersMiddleware:
    """Adds hardening headers to every HTTP response.

    HSTS only when `hsts=True` (HTTPS deployments). Headers already set by the app are
    kept (`setdefault`). Paths in `csp_exempt_paths` (Swagger UI, ReDoc) skip the CSP,
    which would leave them blank: they load scripts and styles from a CDN.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        hsts: bool = False,
        hsts_max_age: int = 31536000,
        csp_exempt_paths: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.hsts = hsts
        self.hsts_max_age = hsts_max_age
        self.csp_exempt_paths = frozenset(csp_exempt_paths)

    @staticmethod
    def _path(scope: Scope) -> str:
        # Behind a proxy with a prefix, `path` includes root_path; exempt paths do not.
        path: str = scope.get("path", "")
        root_path: str = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            return path[len(root_path) :] or "/"
        return path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        apply_csp = self._path(scope) not in self.csp_exempt_paths

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("X-Frame-Options", "DENY")
                headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
                if apply_csp:
                    headers.setdefault("Content-Security-Policy", CSP)
                if self.hsts:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        f"max-age={self.hsts_max_age}; includeSubDomains",
                    )
            await send(message)

        await self.app(scope, receive, send_wrapper)
