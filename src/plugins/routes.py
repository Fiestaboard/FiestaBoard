"""FastAPI router for the ``/plugins`` endpoint family.

Handlers moved out of ``src/api_server.py`` in #1757; Phase 2 slice 4 then
applied ``docs/internal/reference/API_CONVENTIONS.md`` to them and retired the
call-time ``from src.api_server import ...`` seams the move left behind.

Collaborators now resolve from their canonical homes at **module import
time**, so this module never loads ``src.api_server``
(``tests/test_plugins_decoupled.py`` asserts that in a fresh interpreter).
Tests that need to stub a collaborator patch it where this module binds it —
``src.plugins.routes.<name>`` — not ``src.api_server.<name>``.

Where the collaborators went, for the reader chasing a patch target:

===========================================  ==================================
Was                                          Now
===========================================  ==================================
``api_server.get_plugin_registry``           ``src.plugins``
``api_server.get_config_manager``            ``src.config_manager``
``api_server.unmask_sensitive_values``       ``src.config_manager``
``api_server.get_page_service``              ``src.pages.service``
``api_server.get_settings_service``          ``src.settings.service``
``api_server.get_template_engine``           ``src.templates.engine``
``api_server.reset_template_engine``         ``src.templates.engine``
``api_server.reset_display_service``         ``src.displays.service``
``api_server.PLUGIN_SYSTEM_AVAILABLE``       ``src.plugins.routes`` (defined
                                             here; api_server imports it)
the 13 ``PLUGIN_OPTIONS_*`` names            ``src.plugins.options_runtime``
                                             (new)
===========================================  ==================================

**Error translation lives here, and only here.** ``PluginService`` raises the
domain exceptions in :mod:`src.plugins.errors`; ``_STATUS_BY_ERROR`` below is
the single table mapping them to status codes, applied by the
``@plugin_errors_to_http`` decorator on every handler that can reach the
service. Phase 1 had the service raising ``fastapi.HTTPException`` at 25
sites, which made it the one service in the tree that knew about HTTP.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from fastapi import APIRouter, HTTPException, Request

from src.api_errors import errors
from src.config_manager import get_config_manager, unmask_sensitive_values
from src.displays.service import reset_display_service
from src.pages.service import get_page_service
from src.settings.service import get_settings_service
from src.templates.engine import get_template_engine, reset_template_engine

from .errors import (
    PluginConfigInvalid,
    PluginError,
    PluginNotEnabled,
    PluginNotFound,
    PluginOperationFailed,
    PluginOperationRejected,
    PluginOptionsThrottled,
)
from .models import (
    AllPluginVariablesResponse,
    ExternalPluginInstallRequest,
    PluginConfigRequest,
    PluginConfigUpdateResponse,
    PluginDataResponse,
    PluginDemoPageCreateResponse,
    PluginDemoPageResponse,
    PluginDetail,
    PluginEnablementResponse,
    PluginErrorsResponse,
    PluginInstallResponse,
    PluginInstanceCreateRequest,
    PluginInstanceResponse,
    PluginInstancesResponse,
    PluginListResponse,
    PluginManifestResponse,
    PluginOptionsRequest,
    PluginOptionsResponse,
    PluginReceiveResponse,
    PluginSummary,
    PluginUninstallResponse,
    PluginUpdateCheckResponse,
    PluginUpdateResponse,
    PluginUpdatesApplyResponse,
    PluginUpdatesResponse,
    PluginVariablesResponse,
    RegistryListResponse,
)
from .options_runtime import (
    PLUGIN_OPTIONS_MAX_CURSOR_CHARS,
    PLUGIN_OPTIONS_MAX_RETURNED,
    PLUGIN_OPTIONS_TIMEOUT_SECONDS,
    _bounded_options_call,
    _config_fingerprint,
    _declared_options_ids,
    _fit_options_payload,
    _options_cache_seconds,
    _plugin_options_cache_get,
    _plugin_options_cache_key,
    _plugin_options_cache_put,
    _plugin_options_refresh_throttle,
    _serialise_options,
    _stale_options_payload,
    _truncate,
)
from .service import PluginService

try:  # pragma: no cover - the except arm needs a broken install to reach
    from . import get_plugin_registry

    PLUGIN_SYSTEM_AVAILABLE = True
except ImportError:  # pragma: no cover
    PLUGIN_SYSTEM_AVAILABLE = False
    get_plugin_registry = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plugins"])


# ── Error translation ───────────────────────────────────────────────────────

#: The single place a plugin-domain failure becomes a status code. Ordered
#: most-specific first, because ``PluginError`` is the catch-all base.
_STATUS_BY_ERROR: tuple[tuple[type[PluginError], int], ...] = (
    (PluginNotFound, 404),
    (PluginNotEnabled, 400),
    (PluginConfigInvalid, 400),
    (PluginOptionsThrottled, 429),
    (PluginOperationRejected, 400),
    (PluginOperationFailed, 500),
)

_T = TypeVar("_T")


def _as_http(exc: PluginError) -> HTTPException:
    """Translate a domain error into the HTTP failure the API serves."""
    status = next((code for kind, code in _STATUS_BY_ERROR if isinstance(exc, kind)), 400)
    if isinstance(exc, PluginConfigInvalid):
        # The one structured detail in this domain: schema validation produces
        # per-field messages and the settings form highlights the field that
        # is wrong. ``message`` is present because API_CONVENTIONS.md requires
        # a dict detail to carry one — an ``errors``-only body was the exact
        # anti-pattern the doc bans.
        return HTTPException(status_code=status, detail={"message": str(exc), "errors": exc.errors})
    return HTTPException(status_code=status, detail=str(exc))


def plugin_errors_to_http(handler: Callable[..., Awaitable[_T]]) -> Callable[..., Awaitable[_T]]:
    """Map :class:`~src.plugins.errors.PluginError` onto ``HTTPException``.

    Applied to every handler that can reach ``PluginService`` so the service
    never has to know a status code. ``functools.wraps`` keeps the wrapped
    signature visible to FastAPI's dependency resolution and to the
    conventions ratchet, which unwraps before reading handler source.
    """

    @functools.wraps(handler)
    async def wrapper(*args: Any, **kwargs: Any) -> _T:
        try:
            return await handler(*args, **kwargs)
        except PluginError as exc:
            raise _as_http(exc) from exc

    return wrapper


def _require_plugin_system() -> None:
    """503 unless the plugin system imported successfully at startup."""
    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Plugin system is not available.")


def _plugin_service() -> PluginService:
    """Build a PluginService wired to this module's collaborator bindings.

    Resolved through the module globals so a test can steer the service by
    patching ``src.plugins.routes.get_plugin_registry`` (and friends) — one
    seam per collaborator, in the module that uses it.
    """
    return PluginService(
        registry=get_plugin_registry(),
        config_manager=get_config_manager(),
        reset_display=reset_display_service,
        reset_template=reset_template_engine,
    )


# ── Listing and cross-plugin reads ──────────────────────────────────────────


@router.get(
    "/plugins",
    response_model=PluginListResponse,
    responses=errors(503),
)
async def list_plugins() -> PluginListResponse:
    """List all available plugins with their status, metadata and masked config."""
    _require_plugin_system()

    registry = get_plugin_registry()
    plugins = registry.list_plugins()

    config_manager = get_config_manager()
    service = _plugin_service()
    for plugin in plugins:
        plugin_config = config_manager.get_plugin_config(plugin["id"])
        plugin["configured"] = bool(plugin_config)
        plugin["config"] = service.mask_config(plugin_config)

    return PluginListResponse(
        plugins=[PluginSummary.model_validate(p) for p in plugins],
        plugin_system_enabled=True,
        total=len(plugins),
        enabled_count=sum(1 for p in plugins if p.get("enabled", False)),
    )


@router.get("/plugins/variables/all", response_model=AllPluginVariablesResponse)
async def get_all_plugin_variables() -> AllPluginVariablesResponse:
    """Every template variable exposed by the plugin system, for the editor."""
    if not PLUGIN_SYSTEM_AVAILABLE:
        # Fall back to legacy variables rather than failing: the template
        # editor still has a vocabulary without the plugin system.
        template_engine = get_template_engine()
        return AllPluginVariablesResponse(
            variables=template_engine.get_available_variables(),
            max_lengths=template_engine.get_variable_max_lengths(),
            plugin_system_enabled=False,
        )

    registry = get_plugin_registry()
    return AllPluginVariablesResponse(
        variables=registry.get_all_variables(),
        max_lengths=registry.get_all_max_lengths(),
        plugin_system_enabled=True,
    )


@router.get("/plugins/errors", response_model=PluginErrorsResponse)
async def get_plugin_errors() -> PluginErrorsResponse:
    """Report why plugins are not contributing data.

    Two independent failure modes in one payload, because the UI asks one
    question. ``errors`` is load time — the plugin never imported.
    ``fetch_breakers`` is run time — it imported fine and then stopped
    answering, so the circuit breaker (#1884) stopped submitting it. The
    breaker has existed since the pool-starvation fix and until this slice was
    unobservable: a plugin could sit quarantined for minutes while the UI
    showed nothing but stale variables.
    """
    if not PLUGIN_SYSTEM_AVAILABLE:
        return PluginErrorsResponse(errors={}, fetch_breakers={}, plugin_system_enabled=False)

    registry = get_plugin_registry()
    return PluginErrorsResponse(
        errors=registry.get_load_errors(),
        fetch_breakers=registry.get_fetch_breaker_status(),
        plugin_system_enabled=True,
    )


@router.get(
    "/plugins/registry",
    response_model=RegistryListResponse,
    responses=errors(503),
)
async def list_registry_plugins() -> RegistryListResponse:
    """List every plugin in the curated registry, with its installation status."""
    _require_plugin_system()

    registry = get_plugin_registry()
    return RegistryListResponse(entries=registry.get_registry_entries(), plugin_system_enabled=True)


@router.get(
    "/plugins/updates",
    response_model=PluginUpdatesResponse,
    responses=errors(503),
)
async def get_plugin_updates() -> PluginUpdatesResponse:
    """Cached update availability for all installed external plugins.

    Refreshed by a background task every 6 hours; call
    ``POST /plugins/updates/check`` to trigger an immediate check.
    """
    _require_plugin_system()

    registry = get_plugin_registry()
    return PluginUpdatesResponse(
        updates=registry.get_update_status(),
        blocked=registry.get_update_blocked_reasons(),
    )


# ── One plugin ──────────────────────────────────────────────────────────────


@router.get(
    "/plugins/{plugin_id}",
    response_model=PluginDetail,
    responses=errors(404, 503),
)
async def get_plugin(plugin_id: str) -> PluginDetail:
    """Manifest, configuration and status for one plugin."""
    _require_plugin_system()

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    # STORED configuration, without the env-var overlay: this response feeds
    # the settings form, and any value baked in here comes straight back in
    # the next save — serving the overlay would freeze env values into
    # config.json (#1864 review). Which keys are currently env-controlled is
    # reported separately in env_overridden_keys, values excluded.
    config_manager = get_config_manager()
    plugin_config = config_manager.get_plugin_config(plugin_id, include_env_overrides=False)
    env_overridden_keys = sorted(config_manager.get_plugin_env_overrides(plugin_id)) if plugin_config else []

    has_demo = manifest.demo is not None
    demo_page_id = None
    if has_demo:
        page_service = get_page_service()
        demo_page = page_service.get_demo_page(plugin_id, device_type="flagship") or page_service.get_demo_page(
            plugin_id
        )
        if demo_page:
            demo_page_id = demo_page.id

    base_id, instance_label = registry.parse_instance_key(plugin_id)
    instances = registry.list_instances(base_id) if not instance_label else []

    return PluginDetail(
        id=plugin_id,
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        author=manifest.author,
        icon=manifest.icon,
        category=manifest.category,
        plugin_type=manifest.plugin_type,
        enabled=registry.is_enabled(plugin_id),
        config=_plugin_service().mask_config(plugin_config),
        env_overridden_keys=env_overridden_keys,
        settings_schema=manifest.settings_schema,
        variables=manifest.raw.get("variables", {}),
        max_lengths=manifest.max_lengths,
        env_vars=manifest.env_vars,
        documentation=manifest.documentation,
        has_demo=has_demo,
        demo_page_id=demo_page_id,
        instance_label=instance_label,
        base_plugin_id=base_id,
        instances=instances,
    )


@router.get(
    "/plugins/{plugin_id}/manifest",
    response_model=PluginManifestResponse,
    responses=errors(404, 503),
)
async def get_plugin_manifest(plugin_id: str) -> PluginManifestResponse:
    """The full raw manifest, for UI rendering."""
    _require_plugin_system()

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    return PluginManifestResponse.model_validate(manifest.raw)


@router.put(
    "/plugins/{plugin_id}/config",
    response_model=PluginConfigUpdateResponse,
    responses=errors(400, 404, 503),
)
@plugin_errors_to_http
async def update_plugin_config(plugin_id: str, request: PluginConfigRequest) -> PluginConfigUpdateResponse:
    """Validate, persist and apply a plugin's configuration.

    A sensitive field posted back as ``"***"`` resolves to the stored secret;
    see ``PluginService.update_plugin_config`` and
    ``tests/test_plugins_contract.py`` for the whole round-trip contract.
    """
    _require_plugin_system()

    masked = _plugin_service().update_plugin_config(plugin_id, request.config)
    return PluginConfigUpdateResponse(plugin_id=plugin_id, config=masked)


@router.post(
    "/plugins/{plugin_id}/enable",
    response_model=PluginEnablementResponse,
    responses=errors(400, 404, 503),
)
@plugin_errors_to_http
async def enable_plugin(plugin_id: str) -> PluginEnablementResponse:
    """Enable a plugin in the registry and persist the flag to config."""
    _require_plugin_system()

    _plugin_service().enable_plugin(plugin_id)
    return PluginEnablementResponse(plugin_id=plugin_id, enabled=True)


@router.post(
    "/plugins/{plugin_id}/disable",
    response_model=PluginEnablementResponse,
    responses=errors(400, 404, 503),
)
@plugin_errors_to_http
async def disable_plugin(plugin_id: str) -> PluginEnablementResponse:
    """Disable a plugin in the registry and persist the flag to config."""
    _require_plugin_system()

    _plugin_service().disable_plugin(plugin_id)
    return PluginEnablementResponse(plugin_id=plugin_id, enabled=False)


@router.get(
    "/plugins/{plugin_id}/data",
    response_model=PluginDataResponse,
    responses=errors(400, 404, 503),
)
async def get_plugin_data(plugin_id: str) -> PluginDataResponse:
    """Fetch current data from a plugin.

    ``fetch_plugin_data`` makes network calls, so it runs on a worker thread.
    Inline it seized the single event loop for the whole fetch — the API,
    every board and ``GET /health`` stopped answering until the plugin's
    upstream replied. This handler was the last one still doing that; the
    comment in ``options_runtime`` that used to name it as the bad example is
    now obsolete, and ``tests/test_plugin_data_event_loop.py`` keeps it so.
    """
    _require_plugin_system()

    registry = get_plugin_registry()

    if not registry.get_plugin(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if not registry.is_enabled(plugin_id):
        raise HTTPException(status_code=400, detail=f"Plugin not enabled: {plugin_id}")

    result = await asyncio.to_thread(registry.fetch_plugin_data, plugin_id)

    # 503 when plugin data is unavailable (not configured, auth failure) so
    # monitoring and the request log show it as an error for triage.
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Plugin data not available")

    return PluginDataResponse(
        plugin_id=plugin_id,
        available=result.available,
        data=result.data,
        formatted_lines=result.formatted_lines,
        error=result.error,
    )


@router.get(
    "/plugins/{plugin_id}/variables",
    response_model=PluginVariablesResponse,
    responses=errors(404, 503),
)
async def get_plugin_variables(plugin_id: str) -> PluginVariablesResponse:
    """The variables schema a plugin exposes, for the template editor."""
    _require_plugin_system()

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    return PluginVariablesResponse(
        plugin_id=plugin_id,
        variables=manifest.raw.get("variables", {}),
        max_lengths=manifest.max_lengths,
        color_rules_schema=manifest.raw.get("color_rules_schema", {}),
    )


# ── Remote options ──────────────────────────────────────────────────────────


@router.post(
    "/plugins/{plugin_id}/options/{options_id}",
    response_model=PluginOptionsResponse,
    responses=errors(400, 404, 429, 501, 502, 503, 504),
)
@plugin_errors_to_http
async def get_plugin_options_endpoint(
    plugin_id: str, options_id: str, body: PluginOptionsRequest
) -> PluginOptionsResponse:
    """Browse a plugin's upstream catalog to populate one settings field."""
    from .base import OptionsRequest, OptionsUnavailable

    _require_plugin_system()

    registry = get_plugin_registry()

    if registry.get_plugin(plugin_id) is None:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    manifest = registry.get_manifest(plugin_id)
    if options_id not in _declared_options_ids(manifest):
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' does not declare options provider '{options_id}'",
        )

    limit = max(1, min(body.limit, PLUGIN_OPTIONS_MAX_RETURNED))
    request = OptionsRequest(
        options_id=options_id,
        parent=body.parent,
        query=body.query,
        limit=limit,
        cursor=body.cursor,
    )

    cache_seconds = _options_cache_seconds(manifest, options_id)

    def _envelope(**overrides: Any) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "plugin_id": plugin_id,
            "options_id": options_id,
            "options": [],
            "has_more": False,
            "cursor": None,
            "total": None,
            "error": None,
            "cached": False,
            "stale": False,
            "cache_seconds": cache_seconds,
        }
        payload.update(overrides)
        return payload

    stored_config = dict(registry.get_plugin_config(plugin_id) or {})
    # The form posts back "***" wherever a sensitive field used to be, so the
    # draft has to be un-masked against what is stored or the plugin gets three
    # asterisks as its API key and every lookup fails mid-setup.
    draft_config = unmask_sensitive_values(body.draft_config, stored_config) if body.draft_config else None
    if draft_config:
        # Key names only, never values: a settings dialog is exactly where
        # credentials leak into logs.
        logger.debug(
            "Options request for '%s/%s' carries draft config keys: %s",
            plugin_id,
            options_id,
            sorted(draft_config),
        )

    effective_config = {**stored_config, **(draft_config or {})}
    cache_key = _plugin_options_cache_key(plugin_id, options_id, _config_fingerprint(effective_config), body, limit)

    if body.refresh:
        _plugin_options_refresh_throttle(cache_key)
    elif cache_seconds > 0:
        entry = _plugin_options_cache_get(cache_key)
        if entry is not None and (time.monotonic() - entry[0]) < cache_seconds:
            return PluginOptionsResponse.model_validate({**entry[1], "cached": True, "stale": False})

    try:
        # Never call the plugin inline: get_options() makes network calls, and
        # blocking the event loop here would stall every other request.
        result = await _bounded_options_call(
            lambda: registry.get_plugin_options(plugin_id, options_id, request, draft_config=draft_config),
            PLUGIN_OPTIONS_TIMEOUT_SECONDS,
        )
    except TimeoutError as e:
        logger.warning("Options provider '%s' timed out for plugin '%s'", options_id, plugin_id)
        stale = _stale_options_payload(cache_key, reason=f"Options provider '{options_id}' timed out")
        if stale is not None:
            return PluginOptionsResponse.model_validate(stale)
        raise HTTPException(
            status_code=504,
            detail=f"Options provider '{options_id}' timed out",
        ) from e
    except NotImplementedError as e:
        # The manifest promised a provider the class never implemented, or the
        # plugin is a transition. 501 lets the widget degrade to a plain input.
        raise HTTPException(status_code=501, detail=str(e)) from e
    except KeyError as e:
        # The registry could not build a sandbox: the plugin was uninstalled
        # while its settings dialog was open. Still "no such plugin".
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}") from e
    except OptionsUnavailable as e:
        # Deliberately a 200. "No API key yet" is the *expected* state while
        # the user is still filling the form in; the widget shows the reason
        # inline next to the field instead of a failed-request toast. This is
        # the documented no_200_on_failure exception in
        # tests/conventions_manifest.json.
        return PluginOptionsResponse.model_validate(_envelope(error=str(e)))
    except Exception as e:
        # The traceback (with the plugin's raw error text) is already in the
        # server log; the client gets a static message so plugin exceptions
        # cannot leak keys/URLs/paths (CodeQL py/stack-trace-exposure).
        logger.exception("Options provider '%s' failed for plugin '%s'", options_id, plugin_id)
        stale = _stale_options_payload(cache_key, reason="Options provider failed")
        if stale is not None:
            return PluginOptionsResponse.model_validate(stale)
        raise HTTPException(status_code=502, detail="Options provider failed") from e

    options, truncated = _serialise_options(result.options, limit, plugin_id, options_id)
    payload = _fit_options_payload(
        _envelope(
            options=options,
            has_more=bool(result.has_more) or truncated,
            cursor=_truncate(result.cursor, PLUGIN_OPTIONS_MAX_CURSOR_CHARS),
            total=result.total,
            error=result.error,
        )
    )

    if cache_seconds > 0:
        _plugin_options_cache_put(cache_key, payload)

    return PluginOptionsResponse.model_validate(payload)


# ── Plugin Demo Pages ────────────────────────────────────────────────────────


def _resolve_demo_device_type(demo: dict) -> str:
    """Pick the demo device_type that matches the configured board.

    Walks the user's configured boards in order and returns the first
    device_type that the plugin actually ships a demo for. Falls back to
    any device_type the plugin supports, then to "flagship" as a last
    resort. See issue #942.
    """
    configured: list[str] = []
    try:
        board_settings = get_settings_service().get_board_settings()
        for board in getattr(board_settings, "boards", []) or []:
            dt = board.get("device_type") if isinstance(board, dict) else None
            if dt and dt not in configured:
                configured.append(dt)
    except Exception:
        logger.debug("Could not resolve configured device_type; using plugin default", exc_info=True)

    for dt in configured:
        if dt in demo:
            return dt
    if demo:
        return next(iter(demo))
    return "flagship"


@router.get(
    "/plugins/{plugin_id}/demo-page",
    response_model=PluginDemoPageResponse,
    responses=errors(404, 503),
)
async def get_plugin_demo_page(plugin_id: str, device_type: str = "flagship") -> PluginDemoPageResponse:
    """Whether a demo page exists for this plugin and device type."""
    _require_plugin_system()

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if manifest.demo is None:
        return PluginDemoPageResponse(exists=False, page_id=None, has_demo_template=False)

    has_demo_template = device_type in manifest.demo
    demo_page = get_page_service().get_demo_page(plugin_id, device_type=device_type)
    return PluginDemoPageResponse(
        exists=demo_page is not None,
        page_id=demo_page.id if demo_page else None,
        has_demo_template=has_demo_template,
    )


@router.post(
    "/plugins/{plugin_id}/demo-page",
    response_model=PluginDemoPageCreateResponse,
    status_code=201,
    responses=errors(400, 404, 503),
)
async def create_plugin_demo_page(plugin_id: str, device_type: str | None = None) -> PluginDemoPageCreateResponse:
    """Create (or recreate) the demo page for a plugin and device type.

    When *device_type* is omitted it is resolved from the configured board
    settings, so a Note board does not silently get a Flagship-sized demo page
    (issue #942). The demo page is a singleton per plugin + device type: a
    second call deletes the old one and creates a fresh copy, which is what
    ``recreated`` reports.
    """
    _require_plugin_system()

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if manifest.demo is None:
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' does not include a demo page template.",
        )

    resolved_device_type = device_type or _resolve_demo_device_type(manifest.demo)

    demo_schema = manifest.demo.get(resolved_device_type)
    if demo_schema is None:
        raise HTTPException(
            status_code=400,
            detail=f"Plugin '{plugin_id}' has no demo template for device type '{resolved_device_type}'.",
        )

    required_fields = manifest.settings_schema.get("required", [])
    if required_fields:
        plugin_config = get_config_manager().get_plugin_config(plugin_id) or {}
        missing = [f for f in required_fields if f != "enabled" and not plugin_config.get(f)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Required settings not configured: {', '.join(missing)}. "
                f"Configure them first before creating a demo page.",
            )

    page, recreated = get_page_service().create_demo_page(plugin_id, demo_schema)
    return PluginDemoPageCreateResponse(recreated=recreated, page=page.model_dump())


# ── Plugin Instances ────────────────────────────────────────────────────────


@router.get(
    "/plugins/{plugin_id}/instances",
    response_model=PluginInstancesResponse,
    responses=errors(404, 503),
)
async def list_plugin_instances(plugin_id: str) -> PluginInstancesResponse:
    """List all instances of a plugin (excluding the base)."""
    _require_plugin_system()

    registry = get_plugin_registry()
    base_id, _ = registry.parse_instance_key(plugin_id)

    if not registry.get_plugin(base_id):
        raise HTTPException(status_code=404, detail=f"Plugin not found: {base_id}")

    instances = registry.list_instances(base_id)
    return PluginInstancesResponse(plugin_id=base_id, instances=instances, total=len(instances))


@router.post(
    "/plugins/{plugin_id}/instances",
    response_model=PluginInstanceResponse,
    status_code=201,
    responses=errors(400, 404, 503),
)
@plugin_errors_to_http
async def create_plugin_instance(plugin_id: str, request: PluginInstanceCreateRequest) -> PluginInstanceResponse:
    """Create a new instance of a plugin.

    The new instance starts disabled with an empty configuration and is
    configured and enabled independently through the standard endpoints using
    the compound key ``{plugin_id}:{label}``.
    """
    _require_plugin_system()

    base_id, compound_key = _plugin_service().create_instance(plugin_id, request.label)

    # Report the normalized label — that is the instance the registry holds and
    # the one `{{plugin:label.field}}` template references must use.
    _, instance_label = get_plugin_registry().parse_instance_key(compound_key)

    return PluginInstanceResponse(plugin_id=base_id, instance_label=instance_label, instance_key=compound_key)


@router.delete(
    "/plugins/{plugin_id}/instances/{instance_label}",
    response_model=PluginInstanceResponse,
    responses=errors(400, 404, 503),
)
@plugin_errors_to_http
async def delete_plugin_instance(plugin_id: str, instance_label: str) -> PluginInstanceResponse:
    """Remove an instance from the registry and delete its persisted config."""
    _require_plugin_system()

    base_id, compound_key = _plugin_service().delete_instance(plugin_id, instance_label)
    return PluginInstanceResponse(plugin_id=base_id, instance_label=instance_label, instance_key=compound_key)


# ── Webhooks ────────────────────────────────────────────────────────────────


@router.post(
    "/plugins/{plugin_id}/receive",
    response_model=PluginReceiveResponse,
    responses=errors(400, 403, 404, 405, 503),
)
async def receive_plugin_payload(plugin_id: str, request: Request) -> PluginReceiveResponse:
    """Push a JSON payload to a plugin.

    Lets external systems (CI pipelines, automations) push data to plugins
    that support incoming webhooks. The plugin's ``receive_payload`` is called
    with the parsed body, the raw headers, and the raw bytes for HMAC
    verification.
    """
    _require_plugin_system()

    registry = get_plugin_registry()
    plugin = registry.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    if not registry.is_enabled(plugin_id):
        raise HTTPException(status_code=400, detail=f"Plugin not enabled: {plugin_id}")

    raw_body = await request.body()
    try:
        body = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Request body must be valid JSON") from None

    headers = dict(request.headers)

    try:
        plugin.receive_payload(body, headers, raw_body=raw_body)
    except NotImplementedError:
        raise HTTPException(
            status_code=405,
            detail=f"Plugin '{plugin_id}' does not support receive",
        ) from None
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return PluginReceiveResponse(plugin_id=plugin_id)


# ── External Plugin Management ──────────────────────────────────────────────


@router.post(
    "/plugins/registry/{plugin_id}/install",
    response_model=PluginInstallResponse,
    status_code=201,
    responses=errors(400, 503),
)
@plugin_errors_to_http
async def install_registry_plugin(plugin_id: str) -> PluginInstallResponse:
    """Install a plugin from the curated registry by its id.

    The install shells out to ``git`` (up to 120 s) and then imports the
    plugin package, so it runs in a worker thread — inline it would seize the
    event loop and freeze every other request for the whole clone (#1750).
    """
    _require_plugin_system()

    await _plugin_service().install_from_registry(plugin_id)
    return PluginInstallResponse(plugin_id=plugin_id, message=f"Plugin '{plugin_id}' installed from registry.")


@router.post(
    "/plugins/install",
    response_model=PluginInstallResponse,
    status_code=201,
    responses=errors(400, 503),
)
@plugin_errors_to_http
async def install_external_plugin(request: ExternalPluginInstallRequest) -> PluginInstallResponse:
    """Install a plugin from a public git repository URL.

    The repository does not need to follow the ``fiestaboard-plugin--`` naming
    convention (that only applies to registry plugins). The clone runs in a
    worker thread so a slow or unreachable remote cannot block the event loop
    (#1750).
    """
    _require_plugin_system()

    pid = await _plugin_service().install_from_git(
        request.repository,
        plugin_id=request.plugin_id,
        branch=request.branch,
    )
    return PluginInstallResponse(plugin_id=pid, message=f"Plugin '{pid}' installed from {request.repository}.")


@router.delete(
    "/plugins/{plugin_id}/uninstall",
    response_model=PluginUninstallResponse,
    responses=errors(400, 404, 503),
)
@plugin_errors_to_http
async def uninstall_external_plugin(plugin_id: str) -> PluginUninstallResponse:
    """Uninstall an external plugin. Built-ins cannot be uninstalled."""
    _require_plugin_system()

    _plugin_service().uninstall(plugin_id)
    return PluginUninstallResponse(plugin_id=plugin_id, message=f"Plugin '{plugin_id}' has been uninstalled.")


@router.post(
    "/plugins/updates/check",
    response_model=PluginUpdateCheckResponse,
    responses=errors(503),
)
async def trigger_plugin_update_check() -> PluginUpdateCheckResponse:
    """Trigger an immediate update check for all external plugins.

    Runs ``git ls-remote`` against each external plugin's origin on a worker
    thread so the event loop is not blocked.
    """
    _require_plugin_system()

    registry = get_plugin_registry()
    results = await asyncio.to_thread(registry.check_for_updates)
    return PluginUpdateCheckResponse(
        checked=len(results),
        updates_available=[pid for pid, has_update in results.items() if has_update],
    )


@router.post(
    "/plugins/{plugin_id}/update",
    response_model=PluginUpdateResponse,
    # 500: `apply_update` raises PluginOperationFailed when git or the reload
    # fails, and _STATUS_BY_ERROR maps that to 500. It was undeclared.
    responses=errors(400, 404, 500, 503),
)
@plugin_errors_to_http
async def update_plugin(plugin_id: str) -> PluginUpdateResponse:
    """Fetch the latest commits for an external plugin and reload it."""
    _require_plugin_system()

    await _plugin_service().apply_update(plugin_id)
    return PluginUpdateResponse(plugin_id=plugin_id, message=f"Plugin '{plugin_id}' has been updated and reloaded.")


@router.post(
    "/plugins/updates/apply",
    response_model=PluginUpdatesApplyResponse,
    responses=errors(503),
)
@plugin_errors_to_http
async def apply_all_plugin_updates() -> PluginUpdatesApplyResponse:
    """Fetch and reload every external plugin with a pending update.

    Uses the cached update status from the last check — call
    ``POST /plugins/updates/check`` first for a fresh scan. Deliberately
    answers 200 with partial results when some plugins fail: collapsing an
    N-plugin bulk update into one status code would throw away which
    succeeded.
    """
    _require_plugin_system()

    return PluginUpdatesApplyResponse.model_validate(await _plugin_service().apply_all_updates())
