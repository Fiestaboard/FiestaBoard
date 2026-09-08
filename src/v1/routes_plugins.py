"""``/v1/plugins`` — one catalogue instead of two, one write instead of three.

The internal API publishes the plugin registry twice: ``GET /plugins`` with
eighteen fields and ``GET /displays`` with four, both built from the same
``registry.list_plugins()`` call. It also splits one write — "change this
plugin" — across ``POST /enable``, ``POST /disable`` and ``PUT /config``.
v1 serves one catalogue and one ``PATCH``.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from src.api_errors import errors
from src.plugins import routes as plugins_routes
from src.plugins.models import PluginDetail, PluginReceiveResponse

from .models import PluginData, PluginEntry, PluginListResponse, PluginUpdate
from .router import router


@router.get(
    "/plugins",
    response_model=PluginListResponse,
    responses=errors(503),
    summary="List installed plugins",
    description=(
        "Every plugin installed on this instance, whether or not it is switched on. A plugin is a data source — "
        "weather, transit, a stock ticker — that contributes template variables you can put on a page. `enabled` "
        "says whether it runs; `configured` says whether its required settings have been filled in."
    ),
)
async def list_plugins() -> PluginListResponse:
    listing = await plugins_routes.list_plugins()
    entries = [
        PluginEntry(
            id=plugin.id,
            name=plugin.name,
            version=plugin.version,
            description=plugin.description,
            author=plugin.author,
            category=plugin.category,
            plugin_type=plugin.plugin_type,
            icon=plugin.icon,
            enabled=bool(plugin.enabled),
            configured=bool(plugin.configured),
        )
        for plugin in listing.plugins
    ]
    return PluginListResponse(
        plugins=entries,
        total=len(entries),
        enabled_count=sum(1 for entry in entries if entry.enabled),
    )


@router.get(
    "/plugins/{plugin_id}",
    response_model=PluginDetail,
    responses=errors(404, 503),
    summary="Read one plugin",
    description=(
        "Everything about one plugin: its manifest, the template variables it contributes and their maximum "
        "lengths, its settings schema, and its current configuration. Stored secrets come back masked as `***`; "
        "sending that value back in a `PATCH` leaves the stored secret untouched."
    ),
)
async def get_plugin(plugin_id: str) -> PluginDetail:
    return await plugins_routes.get_plugin(plugin_id)


@router.patch(
    "/plugins/{plugin_id}",
    response_model=PluginDetail,
    responses=errors(400, 404, 503),
    summary="Enable, disable or configure a plugin",
    description=(
        "One call for the three things you can do to a plugin. Send `enabled` to switch it on or off, `config` to "
        "replace its settings, or both — the settings are written first so a plugin is never enabled with a "
        "configuration you meant to replace. Answers with the plugin's full detail, secrets masked."
    ),
)
async def update_plugin(plugin_id: str, request: PluginUpdate) -> PluginDetail:
    provided = request.model_dump(exclude_unset=True)
    if not provided:
        raise HTTPException(status_code=400, detail="Send at least one of enabled or config.")

    if "config" in provided and provided["config"] is not None:
        from src.plugins.models import PluginConfigRequest

        await plugins_routes.update_plugin_config(plugin_id, PluginConfigRequest(config=provided["config"]))

    if "enabled" in provided and provided["enabled"] is not None:
        if provided["enabled"]:
            await plugins_routes.enable_plugin(plugin_id)
        else:
            await plugins_routes.disable_plugin(plugin_id)

    return await plugins_routes.get_plugin(plugin_id)


@router.get(
    "/plugins/{plugin_id}/data",
    response_model=PluginData,
    responses=errors(400, 404, 503),
    summary="Read what a plugin is currently reporting",
    description=(
        "The plugin's latest fetch, in both forms the internal API served separately: `data` is the raw variable "
        "payload a template reads from, and `lines`/`text` are the board-ready rendering of it. `available` is "
        "false, with `error` set, when the plugin is disabled, unconfigured, or its source could not be reached — "
        "a 200, because that is the answer to the question asked. 404 means no such plugin is installed."
    ),
)
@plugins_routes.plugin_errors_to_http
async def get_plugin_data(plugin_id: str) -> PluginData:
    """Report the plugin's state rather than refusing over it.

    The response model published ``available`` and ``error`` from the start,
    but the internal handler this used to delegate to raises 400 for a
    disabled plugin and 503 for one whose fetch failed — so neither field
    could ever be false or set, and the schema documented a state the route
    could not produce. The registry already answers all four unavailable
    cases as a ``PluginResult``; v1 serves that, the way
    ``POST /displays/raw/batch`` already does per source.

    Reaching past that handler to the service is deliberate: it owns the
    400/503 verdict the web UI depends on, and that verdict is not v1's. The
    three ``plugins_routes`` names used here are shared plumbing — the
    availability guard, the wired-up service, and the one error-to-status
    table — not that handler's contract, so v1 resolves the registry through
    exactly the seam every other plugin handler does.
    """
    from src.displays.service import get_display_service

    plugins_routes._require_plugin_system()
    result = await plugins_routes._plugin_service().fetch_data(plugin_id)

    available = bool(result.available)
    lines: list[str] = list(result.formatted_lines or [])
    if not lines and available:
        # The /displays half of the merge. A plugin that publishes no
        # formatted_lines of its own still has a board rendering — the display
        # service falls back to its data's "formatted" key — and GET
        # /displays/{type} is where that used to be readable.
        display = get_display_service().get_display(plugin_id)
        if display.available and display.formatted:
            lines = display.formatted.split("\n")

    return PluginData(
        plugin_id=plugin_id,
        available=available,
        data=result.data,
        lines=lines,
        text="\n".join(lines),
        error=result.error,
    )


@router.post(
    "/plugins/{plugin_id}/receive",
    response_model=PluginReceiveResponse,
    responses=errors(400, 403, 404, 405, 503),
    summary="Push data into a plugin from outside",
    description=(
        "The webhook target. A plugin that declares a `receive` handler accepts a JSON body here and updates what "
        "it reports without polling anything — the way to drive a board from a system FiestaBoard cannot reach out "
        "to. 405 means this plugin does not accept pushes."
    ),
)
async def receive_plugin_payload(plugin_id: str, request: Request) -> PluginReceiveResponse:
    return await plugins_routes.receive_plugin_payload(plugin_id, request)
