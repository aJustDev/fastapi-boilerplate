from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.core.config import settings
from app.core.events.bus import EventBus
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
from app.deps.auth import CurrentUser
from app.deps.events import get_event_bus
from app.deps.repository import get_repo
from app.items.repos.item import ItemRepo
from app.items.schemas.item import ItemCategory, ItemCreate, ItemRead, ItemSortField, ItemUpdate
from app.items.use_cases.create_item import CreateItemUseCase
from app.items.use_cases.delete_item import DeleteItemUseCase
from app.items.use_cases.get_item import GetItemUseCase
from app.items.use_cases.list_items import ListItemsCursorUseCase, ListItemsUseCase
from app.items.use_cases.update_item import UpdateItemUseCase

router = APIRouter(prefix="/items", tags=["Items"])

ItemRepoDep = Annotated[ItemRepo, Depends(get_repo(ItemRepo))]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


@router.get("/filters")
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_filter_options(request: Request, repo: ItemRepoDep, user: CurrentUser):
    categories = await repo.get_distinct_categories()
    priorities = await repo.get_distinct_priorities()
    return {
        "category": categories,
        "priority": priorities,
        "is_active": [True, False],
    }


@router.get("", response_model=PaginatedResponse[ItemRead])
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_items(
    request: Request,
    repo: ItemRepoDep,
    user: CurrentUser,
    page: PageQuery = 1,
    page_size: PageSizeQuery = 20,
    order_by: ItemSortField | None = None,
    order_dir: SortDir = SortDir.ASC,
    name: SearchQuery = None,
    category: ItemCategory | None = None,
    is_active: bool | None = None,
):
    filters: dict[str, object] = {}
    if name is not None:
        filters["name"] = name
    if category is not None:
        filters["category"] = category.value
    if is_active is not None:
        filters["is_active"] = is_active

    uc = ListItemsUseCase(repo)
    items, total = await uc.execute(
        page=page,
        page_size=page_size,
        order_by=order_by.value if order_by else None,
        order_dir=order_dir.value,
        filters=filters or None,
    )
    return PaginatedResponse(
        items=[ItemRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/cursor", response_model=CursorPaginatedResponse[ItemRead])
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def list_items_cursor(
    request: Request,
    repo: ItemRepoDep,
    user: CurrentUser,
    cursor: CursorQuery = None,
    limit: PageSizeQuery = 20,
    order_by: ItemSortField | None = None,
    order_dir: SortDir = SortDir.ASC,
    name: SearchQuery = None,
    category: ItemCategory | None = None,
    is_active: bool | None = None,
):
    filters: dict[str, object] = {}
    if name is not None:
        filters["name"] = name
    if category is not None:
        filters["category"] = category.value
    if is_active is not None:
        filters["is_active"] = is_active

    uc = ListItemsCursorUseCase(repo)
    items, next_cursor, has_more = await uc.execute(
        cursor=cursor,
        limit=limit,
        order_by=order_by.value if order_by else None,
        order_dir=order_dir.value,
        filters=filters or None,
    )
    return CursorPaginatedResponse(
        items=[ItemRead.model_validate(i) for i in items],
        next_cursor=next_cursor,
        has_more=has_more,
    )


@router.get("/{item_id}", response_model=ItemRead)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def get_item(request: Request, item_id: IdPath, repo: ItemRepoDep, user: CurrentUser):
    uc = GetItemUseCase(repo)
    item = await uc.execute(item_id)
    return ItemRead.model_validate(item)


@router.post("", response_model=ItemRead, status_code=201)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def create_item(
    request: Request,
    body: ItemCreate,
    repo: ItemRepoDep,
    user: CurrentUser,
    event_bus: EventBusDep,
):
    uc = CreateItemUseCase(repo, event_bus)
    item = await uc.execute(body.name, user.id, body.description, body.category, body.priority)
    return ItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=ItemRead)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def update_item(
    request: Request,
    item_id: IdPath,
    body: ItemUpdate,
    repo: ItemRepoDep,
    user: CurrentUser,
    event_bus: EventBusDep,
):
    uc = UpdateItemUseCase(repo, event_bus)
    data = body.model_dump(exclude_unset=True)
    item = await uc.execute(item_id, data)
    return ItemRead.model_validate(item)


@router.delete("/{item_id}", status_code=204)
@limiter.limit(settings.RATE_LIMIT_DEFAULT)
async def delete_item(
    request: Request,
    item_id: IdPath,
    repo: ItemRepoDep,
    user: CurrentUser,
    event_bus: EventBusDep,
):
    uc = DeleteItemUseCase(repo, event_bus)
    await uc.execute(item_id)
