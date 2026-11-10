from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import settings
from app.core.events.bus import EventBus
from app.core.exceptions.schemas import (
    BAD_REQUEST,
    FORBIDDEN,
    NOT_FOUND,
    RATE_LIMITED,
    UNAUTHENTICATED,
)
from app.core.ratelimit import limiter
from app.core.schema import (
    CursorPaginatedResponse,
    CursorQuery,
    IdPath,
    PageQuery,
    PageSizeQuery,
    PaginatedResponse,
    SearchQuery,
    SortDir,
)
from app.deps.auth import User, require_permissions
from app.deps.events import get_event_bus
from app.deps.repository import get_repo
from app.items.repos.item import ItemRepo
from app.items.schemas.item import (
    ItemCategory,
    ItemCreate,
    ItemFilterOptions,
    ItemRead,
    ItemSortField,
    ItemUpdate,
)
from app.items.services.access import MANAGE_PERMISSION, Actor
from app.items.use_cases.create_item import CreateItemUseCase
from app.items.use_cases.delete_item import DeleteItemUseCase
from app.items.use_cases.get_filter_options import GetFilterOptionsUseCase
from app.items.use_cases.get_item import GetItemUseCase
from app.items.use_cases.list_items import ListItemsCursorUseCase, ListItemsUseCase
from app.items.use_cases.update_item import UpdateItemUseCase

router = APIRouter(
    prefix="/items",
    tags=["Items"],
    responses={**UNAUTHENTICATED, **FORBIDDEN, **RATE_LIMITED},
)

ItemRepoDep = Annotated[ItemRepo, Depends(get_repo(ItemRepo))]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


def _actor_with(permission: str) -> Callable[..., Awaitable[Actor]]:
    """Dependency: the caller, who must hold `permission` (403 otherwise), as an Actor.

    The permission answers "may this user do this kind of thing"; which items it applies
    to is decided by the use case with the Actor (app/items/services/access.py).
    """

    async def _actor(
        user: Annotated[User, Depends(require_permissions(permission=permission))],
    ) -> Actor:
        return Actor(user_id=user.id, manages_all=user.has_permission(MANAGE_PERMISSION))

    return _actor


Reader = Annotated[Actor, Depends(_actor_with("items:read"))]
Writer = Annotated[Actor, Depends(_actor_with("items:write"))]
Deleter = Annotated[Actor, Depends(_actor_with("items:delete"))]


def _filters(
    name: str | None, category: ItemCategory | None, is_active: bool | None
) -> dict[str, object]:
    filters: dict[str, object] = {}
    if name is not None:
        filters["name"] = name
    if category is not None:
        filters["category"] = category.value
    if is_active is not None:
        filters["is_active"] = is_active
    return filters


@router.get("/filters", response_model=ItemFilterOptions)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_filter_options(request: Request, repo: ItemRepoDep, actor: Reader):
    """The values present in the caller's items, to build filter controls."""
    return await GetFilterOptionsUseCase(repo).execute(actor)


@router.get("", response_model=PaginatedResponse[ItemRead])
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_items(
    request: Request,
    repo: ItemRepoDep,
    actor: Reader,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    order_by: ItemSortField | None = None,
    order_dir: SortDir = SortDir.ASC,
    name: SearchQuery = None,
    category: ItemCategory | None = None,
    is_active: bool | None = None,
):
    """The caller's items, by page number, with the total. `name` is a "contains" filter.

    A holder of `items:manage` gets the items of every owner.
    """
    uc = ListItemsUseCase(repo)
    items, total = await uc.execute(
        actor,
        page=page,
        page_size=page_size,
        order_by=order_by.value if order_by else None,
        order_dir=order_dir.value,
        filters=_filters(name, category, is_active),
    )
    return PaginatedResponse(
        items=[ItemRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cursor", response_model=CursorPaginatedResponse[ItemRead], responses={**BAD_REQUEST})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_items_cursor(
    request: Request,
    repo: ItemRepoDep,
    actor: Reader,
    cursor: CursorQuery = None,
    limit: PageSizeQuery = 20,
    order_by: ItemSortField | None = None,
    order_dir: SortDir = SortDir.ASC,
    name: SearchQuery = None,
    category: ItemCategory | None = None,
    is_active: bool | None = None,
):
    """The caller's items by cursor: pass `next_cursor` of a page to get the next one.

    Keep `order_by` and the filters the same between pages; a cursor issued for another
    order answers 400 `invalid_cursor`.
    """
    uc = ListItemsCursorUseCase(repo)
    items, next_cursor, has_more = await uc.execute(
        actor,
        cursor=cursor,
        limit=limit,
        order_by=order_by.value if order_by else None,
        order_dir=order_dir.value,
        filters=_filters(name, category, is_active),
    )
    return CursorPaginatedResponse(
        items=[ItemRead.model_validate(i) for i in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{item_id}", response_model=ItemRead, responses={**NOT_FOUND})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_item(request: Request, item_id: IdPath, repo: ItemRepoDep, actor: Reader):
    """One item. 404 also for an item that belongs to someone else."""
    uc = GetItemUseCase(repo)
    item = await uc.execute(item_id, actor)
    return ItemRead.model_validate(item)


@router.post("", response_model=ItemRead, status_code=201)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def create_item(
    request: Request,
    body: ItemCreate,
    repo: ItemRepoDep,
    actor: Writer,
    event_bus: EventBusDep,
):
    """Create an item owned by the caller. Publishes `item.created`."""
    uc = CreateItemUseCase(repo, event_bus)
    item = await uc.execute(
        body.name, actor.user_id, body.description, body.category, body.priority
    )
    return ItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=ItemRead, responses={**NOT_FOUND})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def update_item(
    request: Request,
    item_id: IdPath,
    body: ItemUpdate,
    repo: ItemRepoDep,
    actor: Writer,
    event_bus: EventBusDep,
):
    """Change the fields sent; the others stay as they are. Publishes `item.updated`."""
    uc = UpdateItemUseCase(repo, event_bus)
    data = body.model_dump(exclude_unset=True)
    item = await uc.execute(item_id, data, actor)
    return ItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=204, responses={**NOT_FOUND})
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def delete_item(
    request: Request,
    item_id: IdPath,
    repo: ItemRepoDep,
    actor: Deleter,
    event_bus: EventBusDep,
):
    """Delete an item. Publishes `item.deleted`."""
    uc = DeleteItemUseCase(repo, event_bus)
    await uc.execute(item_id, actor)
