"""Route helpers for the meta-tests that walk the whole API."""

from collections.abc import Iterator

from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

from main import app


def iter_api_routes(prefix: str = "/v1") -> Iterator[RouteContext]:
    """Routes mounted under `prefix`, with their full path.

    Walking `app.routes` is not enough: since FastAPI 0.140 the routes of an included
    router stay behind it instead of being flattened. `iter_route_contexts` is what
    FastAPI itself uses to build the OpenAPI schema. Every meta-test using this has a
    "the scanner sees the API" canary, so a future change fails loudly instead of
    passing on zero routes.
    """
    for ctx in iter_route_contexts(app.routes):
        if isinstance(ctx.route, APIRoute) and ctx.path and ctx.path.startswith(prefix):
            yield ctx
