"""FastAPI router for the ``/plugins`` endpoint family (issue #1757).

Handlers moved from ``src/api_server.py``. Names that still live in
``api_server`` — ``PLUGIN_SYSTEM_AVAILABLE``, the service getters, the reset
callables, and the plugin-options machinery/state that the test-suite
monkeypatches as ``src.api_server.<name>`` — are imported *inside* each
handler so they resolve through the api_server module at call time. A
module-level import would both create an import cycle (api_server imports
this router) and detach the handlers from those patches (the #1756 pattern).

Orchestration (mutate → persist → reset-display → reset-template-engine) and
the private-member reaches (``ConfigManager._mask_sensitive``,
``PluginRegistry._update_status``) live in
:class:`src.plugins.service.PluginService`; the handlers here stay thin.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .service import PluginService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["plugins"])


def _require_plugin_system() -> None:
    """503 unless the plugin system imported successfully at startup."""
    from src.api_server import PLUGIN_SYSTEM_AVAILABLE  # patched-in-tests seam — see module docstring

    if not PLUGIN_SYSTEM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Plugin system is not available.")


def _plugin_service() -> PluginService:
    """Build a PluginService wired to api_server's (possibly patched) seams.

    The collaborators are resolved through ``src.api_server`` at call time so
    the suite's ``patch("src.api_server.<name>")`` targets keep steering the
    service exactly as they steered the inline handlers.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        get_config_manager,
        get_plugin_registry,
        reset_display_service,
        reset_template_engine,
    )

    return PluginService(
        registry=get_plugin_registry(),
        config_manager=get_config_manager(),
        reset_display=reset_display_service,
        reset_template=reset_template_engine,
    )


class PluginConfigRequest(BaseModel):
    """Request body for plugin configuration updates."""

    config: dict[str, Any]


class PluginEnableRequest(BaseModel):
    """Request body for enabling/disabling a plugin."""

    enabled: bool


@router.get("/plugins")
async def list_plugins():
    """
    List all available plugins.

    Returns plugins with their status, metadata, and whether they're enabled.
    """
    _require_plugin_system()
    from src.api_server import get_config_manager, get_plugin_registry  # patched-in-tests seam

    registry = get_plugin_registry()
    plugins = registry.list_plugins()

    # Add configuration status (masked)
    config_manager = get_config_manager()
    service = _plugin_service()
    for plugin in plugins:
        plugin_config = config_manager.get_plugin_config(plugin["id"])
        if plugin_config:
            plugin["configured"] = True
            # Add masked config
            plugin["config"] = service.mask_config(plugin_config)
        else:
            plugin["configured"] = False
            plugin["config"] = {}

    return {
        "plugins": plugins,
        "plugin_system_enabled": True,
        "total": len(plugins),
        "enabled_count": sum(1 for p in plugins if p.get("enabled", False)),
    }


@router.get("/plugins/variables/all")
async def get_all_plugin_variables():
    """
    Get all template variables from enabled plugins.

    Returns a combined view of all variables for the template editor.
    """
    from src.api_server import (  # patched-in-tests seam — see module docstring
        PLUGIN_SYSTEM_AVAILABLE,
        get_plugin_registry,
        get_template_engine,
    )

    if not PLUGIN_SYSTEM_AVAILABLE:
        # Fall back to legacy variables
        template_engine = get_template_engine()
        return {
            "variables": template_engine.get_available_variables(),
            "max_lengths": template_engine.get_variable_max_lengths(),
            "plugin_system_enabled": False,
        }

    registry = get_plugin_registry()

    return {
        "variables": registry.get_all_variables(),
        "max_lengths": registry.get_all_max_lengths(),
        "plugin_system_enabled": True,
    }


@router.get("/plugins/errors")
async def get_plugin_errors():
    """
    Get any plugin load errors.

    Returns errors from plugins that failed to load.
    """
    from src.api_server import PLUGIN_SYSTEM_AVAILABLE, get_plugin_registry  # patched-in-tests seam

    if not PLUGIN_SYSTEM_AVAILABLE:
        return {"errors": {}, "plugin_system_enabled": False}

    registry = get_plugin_registry()

    return {"errors": registry.get_load_errors(), "plugin_system_enabled": True}


@router.get("/plugins/registry")
async def list_registry_plugins():
    """
    List all plugins available in the curated plugin registry.

    Returns registry entries with their installation status.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()

    return {
        "entries": registry.get_registry_entries(),
        "plugin_system_enabled": True,
    }


@router.get("/plugins/updates")
async def get_plugin_updates():
    """
    Return cached update availability for all installed external plugins.

    Results are refreshed by a background task every 6 hours.  Call
    ``POST /plugins/updates/check`` to trigger an immediate check.

    ``blocked`` maps plugin ids to the reason an upstream commit was *not*
    offered — currently only "the incoming manifest needs a newer FiestaBoard
    core".  Those plugins appear in ``updates`` as ``False``; the reason is
    what lets the UI say so rather than looking stuck.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()
    return {
        "updates": registry.get_update_status(),
        "blocked": registry.get_update_blocked_reasons(),
    }


@router.get("/plugins/{plugin_id}")
async def get_plugin(plugin_id: str):
    """
    Get details for a specific plugin.

    Returns the plugin's manifest, configuration, and status.
    """
    _require_plugin_system()
    from src.api_server import (  # patched-in-tests seam — see module docstring
        get_config_manager,
        get_page_service,
        get_plugin_registry,
    )

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)

    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    # STORED configuration, without the env-var overlay: this response feeds
    # the settings form, and any value baked in here comes straight back in
    # the next save — serving the overlay would freeze env values into
    # config.json (#1864 review). Which keys are currently env-controlled is
    # reported separately in env_overridden_keys.
    config_manager = get_config_manager()
    plugin_config = config_manager.get_plugin_config(plugin_id, include_env_overrides=False)
    env_overridden_keys = sorted(config_manager.get_plugin_env_overrides(plugin_id)) if plugin_config else []

    # Check for demo page (use flagship as the representative for backwards compat)
    has_demo = manifest.demo is not None
    demo_page_id = None
    if has_demo:
        page_service = get_page_service()
        demo_page = page_service.get_demo_page(plugin_id, device_type="flagship") or page_service.get_demo_page(
            plugin_id
        )
        if demo_page:
            demo_page_id = demo_page.id

    # Instance information
    base_id, instance_label = registry.parse_instance_key(plugin_id)
    instances = registry.list_instances(base_id) if not instance_label else []

    return {
        "id": plugin_id,
        "name": manifest.name,
        "version": manifest.version,
        "description": manifest.description,
        "author": manifest.author,
        "icon": manifest.icon,
        "category": manifest.category,
        # "data" or "transition" -- the UI hides the enable toggle for
        # transition plugins, which run whenever selected regardless of it.
        "plugin_type": manifest.plugin_type,
        "enabled": registry.is_enabled(plugin_id),
        "config": _plugin_service().mask_config(plugin_config),
        # Config keys whose live value currently comes from an env var (the
        # values themselves are deliberately NOT in "config").
        "env_overridden_keys": env_overridden_keys,
        "settings_schema": manifest.settings_schema,
        "variables": manifest.raw.get("variables", {}),
        "max_lengths": manifest.max_lengths,
        "env_vars": manifest.env_vars,
        "documentation": manifest.documentation,
        "has_demo": has_demo,
        "demo_page_id": demo_page_id,
        "instance_label": instance_label,
        "base_plugin_id": base_id,
        "instances": instances,
    }


@router.get("/plugins/{plugin_id}/manifest")
async def get_plugin_manifest(plugin_id: str):
    """
    Get the full manifest for a plugin.

    Returns the raw manifest data for UI rendering.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)

    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    return manifest.raw


@router.put("/plugins/{plugin_id}/config")
async def update_plugin_config(plugin_id: str, request: PluginConfigRequest):
    """
    Update configuration for a plugin.

    Args:
        plugin_id: Plugin identifier
        request: Configuration to apply

    Example body:
    {
        "config": {
            "api_key": "your-api-key",
            "location": "San Francisco, CA",
            "refresh_seconds": 300
        }
    }
    """
    _require_plugin_system()

    masked = _plugin_service().update_plugin_config(plugin_id, request.config)

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "config": masked,
    }


@router.post("/plugins/{plugin_id}/enable")
async def enable_plugin(plugin_id: str):
    """
    Enable a plugin.

    Enables the plugin in both the registry and persists to config.
    """
    _require_plugin_system()

    _plugin_service().enable_plugin(plugin_id)

    return {"status": "success", "plugin_id": plugin_id, "enabled": True}


@router.post("/plugins/{plugin_id}/disable")
async def disable_plugin(plugin_id: str):
    """
    Disable a plugin.

    Disables the plugin in both the registry and persists to config.
    """
    _require_plugin_system()

    _plugin_service().disable_plugin(plugin_id)

    return {"status": "success", "plugin_id": plugin_id, "enabled": False}


@router.get("/plugins/{plugin_id}/data")
async def get_plugin_data(plugin_id: str):
    """
    Fetch current data from a plugin.

    Returns the plugin's latest data, formatted output, and status.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()

    if not registry.get_plugin(plugin_id):
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if not registry.is_enabled(plugin_id):
        raise HTTPException(status_code=400, detail=f"Plugin not enabled: {plugin_id}")

    result = registry.fetch_plugin_data(plugin_id)

    # Return 503 when plugin data is unavailable (e.g. not configured, auth failure)
    # so monitoring (Grafana) and request log show it as an error for triage
    if not result.available:
        raise HTTPException(status_code=503, detail=result.error or "Plugin data not available")

    return {
        "plugin_id": plugin_id,
        "available": result.available,
        "data": result.data,
        "formatted_lines": result.formatted_lines,
        "error": result.error,
    }


@router.get("/plugins/{plugin_id}/variables")
async def get_plugin_variables(plugin_id: str):
    """
    Get template variables exposed by a plugin.

    Returns the variables schema for use in the template editor.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)

    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    return {
        "plugin_id": plugin_id,
        "variables": manifest.raw.get("variables", {}),
        "max_lengths": manifest.max_lengths,
        "color_rules_schema": manifest.raw.get("color_rules_schema", {}),
    }


class PluginOptionsRequestBody(BaseModel):
    """Body for ``POST /plugins/{plugin_id}/options/{options_id}``.

    POST rather than GET on purpose: ``parent`` holds arbitrary JSON, and
    ``draft_config`` carries credentials that must never reach a URL, an
    access log, or browser history.
    """

    parent: dict[str, Any] = Field(default_factory=dict)
    query: str = ""
    limit: int = 200
    cursor: str | None = None
    refresh: bool = False
    draft_config: dict[str, Any] = Field(default_factory=dict)


@router.post("/plugins/{plugin_id}/options/{options_id}")
async def get_plugin_options_endpoint(plugin_id: str, options_id: str, body: PluginOptionsRequestBody):
    """Browse a plugin's upstream catalog to populate one settings field."""
    import time

    # Deliberately api_server's logger, not this module's: the never-log-a-
    # draft-credential contract is pinned by a caplog test listening on the
    # "src.api_server" logger (test_plugin_options_route.py).
    from src.api_server import (  # patched-in-tests seam — the options caches/limits are api_server module state
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
        get_plugin_registry,
        logger,
        unmask_sensitive_values,
    )

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
            return {**entry[1], "cached": True, "stale": False}

    try:
        # Never call the plugin inline: get_options() makes network calls, and
        # blocking the event loop here would stall every other request in the
        # process. (GET /plugins/{id}/data still does this; do not copy it.)
        result = await _bounded_options_call(
            lambda: registry.get_plugin_options(plugin_id, options_id, request, draft_config=draft_config),
            PLUGIN_OPTIONS_TIMEOUT_SECONDS,
        )
    except TimeoutError as e:
        logger.warning("Options provider '%s' timed out for plugin '%s'", options_id, plugin_id)
        stale = _stale_options_payload(cache_key, reason=f"Options provider '{options_id}' timed out")
        if stale is not None:
            return stale
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
        # inline next to the field instead of a failed-request toast.
        return _envelope(error=str(e))
    except Exception as e:
        # The traceback (with the plugin's raw error text) is already in the
        # server log; the client gets a static message so plugin exceptions
        # cannot leak keys/URLs/paths (CodeQL py/stack-trace-exposure).
        logger.exception("Options provider '%s' failed for plugin '%s'", options_id, plugin_id)
        stale = _stale_options_payload(cache_key, reason="Options provider failed")
        if stale is not None:
            return stale
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

    return payload


# ── Plugin Demo Pages ────────────────────────────────────────────────────────


def _resolve_demo_device_type(demo: dict) -> str:
    """Pick the demo device_type that matches the configured board.

    Walks the user's configured boards in order and returns the first
    device_type that the plugin actually ships a demo for. Falls back to
    any device_type the plugin supports, then to "flagship" as a last
    resort. See issue #942.
    """
    from src.api_server import get_settings_service  # patched-in-tests seam — see module docstring

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


@router.get("/plugins/{plugin_id}/demo-page")
async def get_plugin_demo_page(plugin_id: str, device_type: str = "flagship"):
    """
    Check whether a demo page exists for this plugin and device type.

    Returns ``exists: true`` and the page id when one is found.
    """
    _require_plugin_system()
    from src.api_server import get_page_service, get_plugin_registry  # patched-in-tests seam

    registry = get_plugin_registry()
    manifest = registry.get_manifest(plugin_id)
    if not manifest:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")

    if manifest.demo is None:
        return {"exists": False, "page_id": None, "has_demo_template": False}

    has_demo_template = device_type in manifest.demo
    page_service = get_page_service()
    demo_page = page_service.get_demo_page(plugin_id, device_type=device_type)
    return {
        "exists": demo_page is not None,
        "page_id": demo_page.id if demo_page else None,
        "has_demo_template": has_demo_template,
    }


@router.post("/plugins/{plugin_id}/demo-page")
async def create_plugin_demo_page(plugin_id: str, device_type: str | None = None):
    """
    Create (or recreate) the demo page for a plugin and device type.

    When *device_type* is omitted, it is resolved from the configured board
    settings (the first device type listed under Settings → Hardware), so a
    Note board does not silently get a Flagship-sized demo page (issue #942).
    If the plugin does not ship a demo template for the configured device,
    we fall back to any device type it does support.

    The demo page is a singleton per plugin + device type -- calling this endpoint
    when a demo page already exists for that device type will delete the old one
    and create a fresh copy.
    """
    _require_plugin_system()
    from src.api_server import (  # patched-in-tests seam — see module docstring
        get_config_manager,
        get_page_service,
        get_plugin_registry,
    )

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

    # Check that required settings are configured
    settings_schema = manifest.settings_schema
    required_fields = settings_schema.get("required", [])
    if required_fields:
        config_manager = get_config_manager()
        plugin_config = config_manager.get_plugin_config(plugin_id) or {}
        missing = [f for f in required_fields if f != "enabled" and not plugin_config.get(f)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Required settings not configured: {', '.join(missing)}. "
                f"Configure them first before creating a demo page.",
            )

    page_service = get_page_service()
    page, recreated = page_service.create_demo_page(plugin_id, demo_schema)

    return {
        "status": "recreated" if recreated else "created",
        "page": page.model_dump(),
    }


# ── Plugin Instances ────────────────────────────────────────────────────────


class PluginInstanceCreateRequest(BaseModel):
    """Request body for creating a new plugin instance."""

    label: str


@router.get("/plugins/{plugin_id}/instances")
async def list_plugin_instances(plugin_id: str):
    """
    List all instances of a plugin.

    Returns the instances (excluding the base) for the given plugin.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()

    # Resolve base plugin id (strip instance label if present)
    base_id, _ = registry.parse_instance_key(plugin_id)

    if not registry.get_plugin(base_id):
        raise HTTPException(status_code=404, detail=f"Plugin not found: {base_id}")

    instances = registry.list_instances(base_id)

    return {
        "plugin_id": base_id,
        "instances": instances,
        "total": len(instances),
    }


@router.post("/plugins/{plugin_id}/instances")
async def create_plugin_instance(plugin_id: str, request: PluginInstanceCreateRequest):
    """
    Create a new instance of a plugin.

    The new instance starts disabled with an empty configuration.
    It can be configured and enabled independently via the standard
    plugin config/enable endpoints using the compound key
    ``{plugin_id}:{label}``.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    service = _plugin_service()
    base_id, compound_key = service.create_instance(plugin_id, request.label)

    # Report the normalized label — that is the instance the registry holds and
    # the one `{{plugin:label.field}}` template references must use.
    _, instance_label = get_plugin_registry().parse_instance_key(compound_key)

    return {
        "status": "success",
        "plugin_id": base_id,
        "instance_label": instance_label,
        "instance_key": compound_key,
        "message": f"Instance '{instance_label}' created for plugin '{base_id}'.",
    }


@router.delete("/plugins/{plugin_id}/instances/{instance_label}")
async def delete_plugin_instance(plugin_id: str, instance_label: str):
    """
    Delete a plugin instance.

    Removes the instance from the registry and its persisted configuration.
    """
    _require_plugin_system()

    base_id, compound_key = _plugin_service().delete_instance(plugin_id, instance_label)

    return {
        "status": "success",
        "plugin_id": base_id,
        "instance_label": instance_label,
        "instance_key": compound_key,
        "message": f"Instance '{instance_label}' of plugin '{base_id}' deleted.",
    }


@router.post("/plugins/{plugin_id}/receive")
async def receive_plugin_payload(plugin_id: str, request: Request):
    """
    Push a JSON payload to a plugin.

    Allows external systems (CI pipelines, automations, etc.) to push data to
    plugins that support incoming webhooks.  The plugin's ``receive_payload``
    method is called with the parsed body, the raw request headers, and the
    raw body bytes (for HMAC verification).

    Returns 404 when the plugin is not found, 400 when it is not enabled or
    the body is not valid JSON, 403 when the plugin rejects the request due to
    a signature mismatch, and 405 when the plugin does not support receive.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

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

    return {"status": "ok"}


# ── External Plugin Management ──────────────────────────────────────────────


class ExternalPluginInstallRequest(BaseModel):
    """Request body for installing an external plugin."""

    repository: str
    plugin_id: str | None = None
    branch: str = ""


@router.post("/plugins/registry/{plugin_id}/install")
async def install_registry_plugin(plugin_id: str):
    """
    Install a plugin from the curated registry by its id.

    The install shells out to ``git`` (up to 120 s) and then imports the
    plugin package, so it runs in a worker thread — inline it would seize the
    event loop and freeze every other request for the whole clone (#1750).
    """
    _require_plugin_system()

    await _plugin_service().install_from_registry(plugin_id)

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "message": f"Plugin '{plugin_id}' installed from registry.",
    }


@router.post("/plugins/install")
async def install_external_plugin(request: ExternalPluginInstallRequest):
    """
    Install a plugin from a public git repository URL.

    The repository does not need to follow the ``fiestaboard-plugin--``
    naming convention (that requirement only applies to registry plugins).

    The clone runs in a worker thread so a slow or unreachable remote cannot
    block the event loop (#1750).
    """
    _require_plugin_system()

    pid = await _plugin_service().install_from_git(
        request.repository,
        plugin_id=request.plugin_id,
        branch=request.branch,
    )

    return {
        "status": "success",
        "plugin_id": pid,
        "message": f"Plugin '{pid}' installed from {request.repository}.",
    }


@router.delete("/plugins/{plugin_id}/uninstall")
async def uninstall_external_plugin(plugin_id: str):
    """
    Uninstall an external (non-built-in) plugin.

    Built-in plugins shipped with FiestaBoard cannot be uninstalled.
    """
    _require_plugin_system()

    _plugin_service().uninstall(plugin_id)

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "message": f"Plugin '{plugin_id}' has been uninstalled.",
    }


@router.post("/plugins/updates/check")
async def trigger_plugin_update_check():
    """
    Trigger an immediate update check for all external plugins.

    Runs ``git ls-remote`` against each external plugin's origin in a thread
    pool so the event loop is not blocked.
    """
    _require_plugin_system()
    from src.api_server import get_plugin_registry  # patched-in-tests seam — see module docstring

    registry = get_plugin_registry()
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(None, registry.check_for_updates)
    plugins_with_updates = [pid for pid, has_update in results.items() if has_update]
    return {
        "checked": len(results),
        "updates_available": plugins_with_updates,
    }


@router.post("/plugins/{plugin_id}/update")
async def update_plugin(plugin_id: str):
    """
    Fetch the latest commits for an external plugin from its remote and reload it.

    Built-in plugins cannot be updated via this endpoint.
    """
    _require_plugin_system()

    await _plugin_service().apply_update(plugin_id)

    return {
        "status": "success",
        "plugin_id": plugin_id,
        "message": f"Plugin '{plugin_id}' has been updated and reloaded.",
    }


@router.post("/plugins/updates/apply")
async def apply_all_plugin_updates():
    """
    Fetch and reload all external plugins that have a pending update.

    Uses the cached update status from the last check — call
    ``POST /plugins/updates/check`` first if you want a fresh scan before
    applying.  Returns 200 even when some plugins fail so the caller can
    inspect partial results.
    """
    _require_plugin_system()

    return await _plugin_service().apply_all_updates()
