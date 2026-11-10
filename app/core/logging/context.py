"""Values that belong to the request being served, readable from any layer."""

from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# Id of the authenticated user, as text. Set by `get_current_user`, cleared for each
# request by RequestIdMiddleware; None outside a request and for anonymous routes.
actor_var: ContextVar[str | None] = ContextVar("actor", default=None)


def get_request_id() -> str:
    return request_id_var.get()


def get_actor() -> str | None:
    return actor_var.get()
