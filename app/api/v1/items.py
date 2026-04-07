from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.events.bus import EventBus
from app.deps.auth import CurrentUser
from app.deps.events import get_event_bus
from app.deps.repository import get_repo
from app.repos.items.item import ItemRepo
from app.schemas.items.item import ItemCategory, ItemCreate, ItemRead, ItemSortField, ItemUpdate
from app.schemas.pagination import CursorPaginatedResponse, PaginatedResponse, SortDir
from app.use_cases.items.create_item import CreateItemUseCase
from app.use_cases.items.delete_item import DeleteItemUseCase
from app.use_cases.items.get_item import GetItemUseCase
from app.use_cases.items.list_items import ListItemsCursorUseCase, ListItemsUseCase
from app.use_cases.items.update_item import UpdateItemUseCase

router = APIRouter(prefix="/items", tags=["Items"])

ItemRepoDep = Annotated[ItemRepo, Depends(get_repo(ItemRepo))]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]


@router.get("/filters")
async def get_filter_options(repo: ItemRepoDep, user: CurrentUser):
    categories = await repo.get_distinct_categories()
    priorities = await repo.get_distinct_priorities()
    return {
        "category": categories,
        "priority": priorities,
        "is_active": [True, False],
    }


@router.get("", response_model=PaginatedResponse[ItemRead])
async def list_items(
    repo: ItemRepoDep,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order_by: ItemSortField | None = None,
    order_dir: SortDir = SortDir.ASC,
    name: str | None = None,
    category: ItemCategory | None = None,
    is_active: bool | None = None,
):
    filters = {}
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
async def list_items_cursor(
    repo: ItemRepoDep,
    user: CurrentUser,
    cursor: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    order_by: ItemSortField | None = None,
    order_dir: SortDir = SortDir.ASC,
    name: str | None = None,
    category: ItemCategory | None = None,
    is_active: bool | None = None,
):
    filters = {}
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
async def get_item(item_id: int, repo: ItemRepoDep, user: CurrentUser):
    uc = GetItemUseCase(repo)
    item = await uc.execute(item_id)
    return ItemRead.model_validate(item)


@router.post("", response_model=ItemRead, status_code=201)
async def create_item(
    body: ItemCreate,
    repo: ItemRepoDep,
    user: CurrentUser,
    event_bus: EventBusDep,
):
    uc = CreateItemUseCase(repo, event_bus)
    item = await uc.execute(body.name, user.id, body.description, body.category, body.priority)
    return ItemRead.model_validate(item)


@router.patch("/{item_id}", response_model=ItemRead)
async def update_item(
    item_id: int,
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
async def delete_item(
    item_id: int,
    repo: ItemRepoDep,
    user: CurrentUser,
    event_bus: EventBusDep,
):
    uc = DeleteItemUseCase(repo, event_bus)
    await uc.execute(item_id)
