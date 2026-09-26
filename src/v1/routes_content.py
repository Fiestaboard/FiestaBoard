"""``/v1/pages``, ``/v1/schedules``, ``/v1/collections`` — the saved content.

Fifteen operations, five per resource, all plain CRUD over the models the
domains already publish. Each handler delegates to the domain router's own
handler, so the validation, the 404 wording and the response shape are one
implementation, not two.

Reusing the domain handlers rather than the services is deliberate: the
domain routers hold the parts a service does not — the transition-plugin
beta gate on a page, the sun-time enrichment on a schedule, the page-exists
checks on a collection's members. Calling the service directly would drop
them silently.
"""

from __future__ import annotations

from src.api_errors import errors
from src.collections import routes as collections_routes
from src.collections.models import (
    Collection,
    CollectionCreate,
    CollectionDeleteResponse,
    CollectionListResponse,
    CollectionUpdate,
)
from src.pages import routes as pages_routes
from src.pages.models import (
    Page,
    PageCreate,
    PageDeleteResponse,
    PageListResponse,
    PageUpdate,
    PageUpdateResponse,
)
from src.schedules import routes as schedules_routes
from src.schedules.models import (
    ScheduleCreate,
    ScheduleDeleteResponse,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdate,
    ScheduleWriteResponse,
)

from .router import router

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@router.get(
    "/pages",
    response_model=PageListResponse,
    responses=errors(503),
    summary="List saved pages",
    description=(
        "Every page saved on this install. A page is a reusable board layout — literal text, plugin variables, or "
        "rows composed from other sources — that a schedule, a collection or `POST /v1/boards/{board}/message` can "
        "refer to by id."
    ),
)
async def list_pages() -> PageListResponse:
    return await pages_routes.list_pages()


@router.post(
    "/pages",
    response_model=Page,
    status_code=201,
    responses=errors(400),
    summary="Create a page",
    description=(
        "Saves a new page and answers with it, including the generated `id` you refer to it by. `type` picks how it "
        "is built: `template` for text with `{{variables}}`, `single` for one plugin's output, `composite` for rows "
        "drawn from several sources. `device_type` must match the boards you intend to show it on."
    ),
)
async def create_page(request: PageCreate) -> Page:
    return await pages_routes.create_page(request)


@router.get(
    "/pages/{page_id}",
    response_model=Page,
    responses=errors(404),
    summary="Read one page",
    description=(
        "The saved page with this id, exactly as stored — its type, its device size, its template or row "
        "configuration, and its per-page transition overrides. 404 when no page has this id."
    ),
)
async def get_page(page_id: str) -> Page:
    return await pages_routes.get_page(page_id)


@router.put(
    "/pages/{page_id}",
    response_model=PageUpdateResponse,
    responses=errors(400, 404),
    summary="Update a page",
    description=(
        "Applies the fields you send and leaves the rest alone. The response carries the updated page plus "
        "`incompatible_references`: places that still point at this page — a board's schedule, a pinned selection — "
        "where your change has made the size no longer fit."
    ),
)
async def update_page(page_id: str, request: PageUpdate) -> PageUpdateResponse:
    return await pages_routes.update_page(page_id, request)


@router.delete(
    "/pages/{page_id}",
    response_model=PageDeleteResponse,
    responses=errors(404),
    summary="Delete a page",
    description=(
        "Removes the page. If it was the last page, or was the one a board was showing, the response says what was "
        "put in its place so nothing is left pointing at a page that no longer exists."
    ),
)
async def delete_page(page_id: str) -> PageDeleteResponse:
    return await pages_routes.delete_page(page_id)


# ---------------------------------------------------------------------------
# Schedules
# ---------------------------------------------------------------------------


@router.get(
    "/schedules",
    response_model=ScheduleListResponse,
    responses=errors(503),
    summary="List schedule entries",
    description=(
        "Every schedule entry, newest rules included. Pass `board_id` to narrow it to one board, or `*` for all "
        "boards at once. Each entry says which page shows between which times, on which days; the response also "
        "carries the fallback page and whether scheduling is switched on."
    ),
)
async def list_schedules(board_id: str | None = None) -> ScheduleListResponse:
    return await schedules_routes.list_schedules(board_id)


@router.post(
    "/schedules",
    response_model=ScheduleWriteResponse,
    status_code=201,
    responses=errors(400, 404),
    summary="Create a schedule entry",
    description=(
        "Adds a rule: show `page_id` from `start_time` to `end_time` on the days `day_pattern` selects. Times may "
        "also be relative to sunrise or sunset (`start_type`, `start_sun_offset`), and a rule may recur weekly, on "
        "a calendar date every year, or once. Omit `board_id` for the default board."
    ),
)
async def create_schedule(request: ScheduleCreate) -> ScheduleWriteResponse:
    return await schedules_routes.create_schedule(request)


@router.get(
    "/schedules/{schedule_id}",
    response_model=ScheduleResponse,
    responses=errors(404),
    summary="Read one schedule entry",
    description=(
        "The schedule entry with this id, plus `resolved_start_time` and `resolved_end_time` — the wall-clock times "
        "a sunrise- or sunset-relative rule works out to today."
    ),
)
async def get_schedule(schedule_id: str) -> ScheduleResponse:
    return await schedules_routes.get_schedule(schedule_id)


@router.put(
    "/schedules/{schedule_id}",
    response_model=ScheduleWriteResponse,
    responses=errors(400, 404),
    summary="Update a schedule entry",
    description=(
        "Applies only the fields you send, so a partial update cannot silently clear the ones you left out. "
        "`warnings` reports rules that now overlap or leave a gap without failing the write."
    ),
)
async def update_schedule(schedule_id: str, request: ScheduleUpdate) -> ScheduleWriteResponse:
    return await schedules_routes.update_schedule(schedule_id, request)


@router.delete(
    "/schedules/{schedule_id}",
    response_model=ScheduleDeleteResponse,
    responses=errors(404),
    summary="Delete a schedule entry",
    description=(
        "Removes this schedule rule. The page it pointed at is untouched, and the board falls back to its "
        "remaining rules — or to its gap page when none of them match."
    ),
)
async def delete_schedule(schedule_id: str) -> ScheduleDeleteResponse:
    return await schedules_routes.delete_schedule(schedule_id)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


@router.get(
    "/collections",
    response_model=CollectionListResponse,
    responses=errors(503),
    summary="List the saved collections",
    description=(
        "Every collection. A collection is a set of pages plus a rule for choosing between them — rotate on a "
        "timer, pick at random, or switch on the value of a template expression — and it can be used anywhere a "
        "page id can."
    ),
)
async def list_collections() -> CollectionListResponse:
    return await collections_routes.list_collections()


@router.post(
    "/collections",
    response_model=Collection,
    status_code=201,
    responses=errors(400),
    summary="Create a collection",
    description=(
        "Saves a set of pages and how to choose between them. `selection_mode` is `time` (rotate every "
        "`time.interval_seconds`), `random`, or `variable` (evaluate `variable.rules` in order and show the first "
        "match). The generated id is prefixed `collection:` and is usable wherever a page id is."
    ),
)
async def create_collection(request: CollectionCreate) -> Collection:
    return await collections_routes.create_collection(request)


@router.get(
    "/collections/{collection_id}",
    response_model=Collection,
    responses=errors(404),
    summary="Read one collection",
    description=(
        "The collection with this id: its member page ids in order, its selection mode, and the config block "
        "for that mode — the rotation interval, or the expression rules that pick between the members."
    ),
)
async def get_collection(collection_id: str) -> Collection:
    return await collections_routes.get_collection(collection_id)


@router.put(
    "/collections/{collection_id}",
    response_model=Collection,
    responses=errors(400, 404),
    summary="Update a collection",
    description=(
        "Applies only the fields you send. Every page id in `page_ids` must exist, and a `variable` rule may only "
        "point at a page the collection contains."
    ),
)
async def update_collection(collection_id: str, request: CollectionUpdate) -> Collection:
    return await collections_routes.update_collection(collection_id, request)


@router.delete(
    "/collections/{collection_id}",
    response_model=CollectionDeleteResponse,
    responses=errors(404),
    summary="Delete a collection",
    description=(
        "Removes the collection. Its member pages are untouched, but anything still referring to the "
        "collection id — a schedule rule, a board's pinned selection — will stop resolving."
    ),
)
async def delete_collection(collection_id: str) -> CollectionDeleteResponse:
    return await collections_routes.delete_collection(collection_id)
