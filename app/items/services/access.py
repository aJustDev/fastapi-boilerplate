"""Who may act on which item.

Two checks, at two levels:
- the route requires a permission (`items:read`, `items:write`, `items:delete`): what kind
  of thing the user may do at all (app/deps/auth.py, `require_permissions`);
- these rules decide on which items: the ones the user owns, or every item for a holder of
  `items:manage`.
"""

from dataclasses import dataclass

from app.core.exceptions import NotFoundError
from app.items.models.item import ItemORM

MANAGE_PERMISSION = "items:manage"


@dataclass(frozen=True, slots=True)
class Actor:
    """The user behind a request, reduced to what the item rules need."""

    user_id: int
    manages_all: bool


def owner_filter(actor: Actor) -> int | None:
    """The owner a listing is limited to; None means every owner."""
    return None if actor.manages_all else actor.user_id


def ensure_access(item: ItemORM | None, item_id: int, actor: Actor) -> ItemORM:
    """The item, if it exists and the actor may act on it.

    Someone else's item is reported as missing, with the same error as an id that does
    not exist: a 403 would tell the caller that the id is taken.
    """
    if item is None or not (actor.manages_all or item.owner_id == actor.user_id):
        raise NotFoundError("Item", item_id)
    return item
