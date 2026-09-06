"""Canonical executors for FiestaBoard operations.

One implementation per operation (issue #1764). Each executor carries the
behavior that used to live inline in an MCP tool body in
:mod:`src.mcp_server`; the MCP tools and the chat grammar
(:mod:`src.ai.chat_ops`, resolved through :mod:`src.ops.registry`) both
dispatch here, so the two surfaces cannot drift again.

Conventions, inherited from the MCP tools so re-expressing them here is
behavior-preserving:

- Executors never raise: failures come back as ``results.err(...)``
  envelopes, successes as ``results.ok(...)``.
- Services are imported lazily inside each executor so tests can patch the
  canonical module locations (``src.pages.service.get_page_service`` etc.)
  and so importing this module never drags in ``api_server``.
- Plugin mutations go through :class:`src.plugins.service.PluginService`
  (#1757/#1588): the registry holds live state, ConfigManager holds
  ``config.json``, and only the service writes both.

Unified semantics decided at #1764 (see the parity suite,
``tests/test_op_parity.py``):

- ``configure_plugin`` MERGES the given keys into the stored config (the
  MCP behavior, pinned by tests/test_mcp_state_effects.py). The chat op
  ``update_plugin_config`` resolves here and gains merge semantics at the
  op layer; ``PUT /plugins/{id}/config`` keeps its replace semantics — it
  is the settings-form endpoint, not an operation surface.
- ``update_schedule`` applies ONLY the fields the caller supplied. The MCP
  tool used to pass every parameter (explicit ``None``s count as *set*
  under ``model_dump(exclude_unset=True)``) and silently wiped
  ``end_time`` on any partial update — the same defect ``update_page``
  was already fixed for.
- ``update_collection`` does not force ``selection_mode`` back to
  ``"time"`` when only the interval changes (the web drawer still does,
  client-side — a #1766 concern).
"""

from __future__ import annotations

import logging
from typing import Any

from .results import err, ok, rest_detail, serialize

logger = logging.getLogger(__name__)


def _plugin_service() -> Any:
    """The shared plugin-orchestration service (never api_server).

    Mirrors the REST layer's 503 guard: when the plugin subsystem cannot
    import, tools report the clean "Plugin system is not available."
    domain error instead of a raw ImportError (#1865 review).
    """
    try:
        from src.plugins.service import PluginService
    except ImportError as exc:
        raise RuntimeError("Plugin system is not available.") from exc

    return PluginService()


# ---------------------------------------------------------------------------
# Plugin operations
# ---------------------------------------------------------------------------


async def install_plugin(
    plugin_id: str,
    auto_enable: bool = True,
    initial_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Install a plugin from the official registry, optionally enable + configure it.

    ``initial_config`` exists only on the chat grammar; when given it is
    applied through :func:`configure_plugin` after a successful enable.
    """
    from fastapi import HTTPException

    try:
        await _plugin_service().install_from_registry(plugin_id)
    except HTTPException as exc:
        return err(f"Error installing plugin '{plugin_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error installing plugin '{plugin_id}': {exc}")

    if auto_enable:
        enabled = enable_plugin(plugin_id)
        if enabled.get("status") == "error":
            return err(f"Plugin '{plugin_id}' was installed but could not be enabled: {enabled['error']}")

    if initial_config:
        configured = configure_plugin(plugin_id, initial_config)
        if configured.get("status") == "error":
            return err(f"Plugin '{plugin_id}' was installed but could not be configured: {configured['error']}")

    state = "installed and enabled" if auto_enable else "installed (disabled)"
    return ok(f"Plugin '{plugin_id}' {state} successfully.", plugin_id=plugin_id, enabled=auto_enable)


def enable_plugin(plugin_id: str) -> dict[str, Any]:
    """Enable an installed but currently-disabled plugin."""
    from fastapi import HTTPException

    try:
        _plugin_service().enable_plugin(plugin_id)
    except HTTPException as exc:
        return err(f"Error enabling plugin '{plugin_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error enabling plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' enabled successfully.", plugin_id=plugin_id)


def disable_plugin(plugin_id: str) -> dict[str, Any]:
    """Disable an installed plugin without uninstalling it."""
    from fastapi import HTTPException

    try:
        _plugin_service().disable_plugin(plugin_id)
    except HTTPException as exc:
        return err(f"Error disabling plugin '{plugin_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error disabling plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' disabled successfully.", plugin_id=plugin_id)


def uninstall_plugin(plugin_id: str) -> dict[str, Any]:
    """Permanently remove an installed plugin. Irreversible."""
    from fastapi import HTTPException

    try:
        _plugin_service().uninstall(plugin_id)
    except HTTPException as exc:
        return err(f"Error uninstalling plugin '{plugin_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error uninstalling plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' uninstalled successfully.", plugin_id=plugin_id)


def configure_plugin(plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Merge the given keys into the plugin's stored config and persist.

    Merge — not replace — so a partial update never drops previously-set
    fields (and never trips required-field validation on the keys it did
    not send). Pinned by tests/test_mcp_state_effects.py.
    """
    from fastapi import HTTPException

    from src.config_manager import get_config_manager

    try:
        # Raw STORED config, WITHOUT the env-var overlay — this merge is
        # persisted, and merging the overlay in would write env secrets
        # into config.json (issue #1761 / #1864 review).
        existing = get_config_manager().get_plugin_config(plugin_id, include_env_overrides=False) or {}
        merged = {**existing, **config}
        masked = _plugin_service().update_plugin_config(plugin_id, merged)
    except HTTPException as exc:
        return err(f"Error configuring plugin '{plugin_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error configuring plugin '{plugin_id}': {exc}")

    return ok(
        f"Configuration updated for '{plugin_id}'.",
        plugin_id=plugin_id,
        config=serialize(masked),
    )


async def update_plugin(plugin_id: str) -> dict[str, Any]:
    """Update an installed plugin from its git remote.

    #1741: goes through ``PluginService.apply_update`` — the shared,
    guarded path — never re-deriving its checks here.
    """
    from fastapi import HTTPException

    try:
        await _plugin_service().apply_update(plugin_id)
    except HTTPException as exc:
        return err(f"Error updating plugin '{plugin_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error updating plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' updated successfully.", plugin_id=plugin_id)


# ---------------------------------------------------------------------------
# Page operations
# ---------------------------------------------------------------------------


def create_page(
    name: str,
    template_lines: list[str],
    device_type: str = "flagship",
    duration_seconds: int = 300,
    line_metadata: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a new template page.

    ``line_metadata`` exists only on the chat grammar (``replace_page``);
    the MCP tool never sends it.
    """
    try:
        from src.pages.models import PageCreate
        from src.pages.service import get_page_service

        svc = get_page_service()
        fields: dict[str, Any] = {
            "name": name,
            "type": "template",
            "device_type": device_type,
            "template": template_lines,
            "duration_seconds": duration_seconds,
        }
        if line_metadata:
            fields["line_metadata"] = line_metadata
        page = svc.create_page(PageCreate(**fields))
        return ok(
            f"Page '{name}' created with id '{page.id}'.",
            page_id=page.id,
            name=page.name,
        )
    except Exception as exc:
        return err(f"Error creating page: {exc}")


def update_page(
    page_id: str,
    name: str | None = None,
    template_lines: list[str] | None = None,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Update an existing page's name, template content, or duration.

    Only fields the caller actually supplied are passed through —
    ``PageService.update_page`` merges with ``model_dump(exclude_unset=True)``,
    where an explicit ``None`` counts as set and would wipe the template.
    """
    try:
        from src.pages.models import PageUpdate
        from src.pages.service import get_page_service

        svc = get_page_service()
        fields: dict[str, Any] = {}
        if name is not None:
            fields["name"] = name
        if template_lines is not None:
            fields["template"] = template_lines
        if duration_seconds is not None:
            fields["duration_seconds"] = duration_seconds
        if not fields:
            return err("Nothing to update: pass at least one of name, template_lines, duration_seconds.")

        page = svc.update_page(page_id, PageUpdate(**fields))
        if page is None:
            return err(f"Page '{page_id}' not found.")
        return ok(f"Page '{page_id}' updated.", page_id=page.id, name=page.name)
    except Exception as exc:
        return err(f"Error updating page '{page_id}': {exc}")


def delete_page(page_id: str) -> dict[str, Any]:
    """Delete a page permanently."""
    try:
        from src.pages.service import get_page_service

        svc = get_page_service()
        result = svc.delete_page(page_id)
        if not result.deleted:
            return err(f"Page '{page_id}' was not deleted (it may not exist).")
        return ok(
            f"Page '{page_id}' deleted successfully.",
            page_id=page_id,
            default_page_created=result.default_page_created,
            new_page_id=result.new_page_id,
            active_page_updated=result.active_page_updated,
        )
    except Exception as exc:
        return err(f"Error deleting page '{page_id}': {exc}")


async def set_active_page(page_id: str, board_id: str | None = None) -> dict[str, Any]:
    """Set which page is currently shown on the display.

    Delegates to the REST handler rather than reimplementing it: selecting
    a page validates the ref, enforces page<->board size compatibility,
    dismisses active plugin triggers (#856), and renders to the board.
    Issue #1559 was a reimplementation going its own way.

    ``board_id`` targets that board's active-page slot (#1765); omitted is
    the legacy primary-board call, exactly as before — the REST handler
    already speaks per-board (#1244), so the parameter simply flows through.
    """
    from fastapi import HTTPException

    from src.api_server import set_active_page as _rest_set_active_page

    body: dict[str, Any] = {"page_id": page_id}
    if board_id is not None:
        body["board_id"] = board_id
    try:
        response = await _rest_set_active_page(body)
    except HTTPException as exc:
        return err(f"Error setting active page: {exc.detail}")
    except Exception as exc:
        return err(f"Error setting active page: {exc}")

    message = f"Active page set to '{page_id}'."
    if board_id is not None:
        message = f"Active page set to '{page_id}' on board '{board_id}'."
    if response.get("paused"):
        message += " The board is paused, so it will appear when you resume it."
    elif not response.get("sent_to_board"):
        message += " It will appear on the board on the next display refresh."
    return ok(
        message,
        page_id=page_id,
        board_id=board_id,
        sent_to_board=bool(response.get("sent_to_board")),
        paused=bool(response.get("paused")),
        warnings=response.get("warnings", []),
    )


# ---------------------------------------------------------------------------
# Schedule operations
# ---------------------------------------------------------------------------


def create_schedule(
    page_id: str,
    start_time: str,
    day_pattern: str = "all",
    end_time: str | None = None,
    enabled: bool = True,
    custom_days: list[str] | None = None,
) -> dict[str, Any]:
    """Create a schedule entry showing a page (or collection) at a time slot.

    ``custom_days`` exists only on the chat grammar (required there when
    ``day_pattern == "custom"``); the MCP tool never sends it.
    """
    try:
        from src.schedules.models import ScheduleCreate
        from src.schedules.service import get_schedule_service

        svc = get_schedule_service()
        fields: dict[str, Any] = {
            "page_id": page_id,
            "start_time": start_time,
            "end_time": end_time,
            "day_pattern": day_pattern,
            "enabled": enabled,
        }
        if custom_days is not None:
            fields["custom_days"] = custom_days
        entry = svc.create_schedule(ScheduleCreate(**fields))
        return ok(
            f"Schedule created: page '{page_id}' from {start_time} on {day_pattern} days.",
            schedule_id=entry.id,
        )
    except Exception as exc:
        return err(f"Error creating schedule: {exc}")


def update_schedule(
    schedule_id: str,
    page_id: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    day_pattern: str | None = None,
    enabled: bool | None = None,
    custom_days: list[str] | None = None,
    clear_end_time: bool = False,
    clear_custom_days: bool = False,
) -> dict[str, Any]:
    """Update an existing schedule entry. Only supplied fields change.

    ``ScheduleService.update_schedule`` merges with
    ``model_dump(exclude_unset=True)`` — an explicit ``None`` counts as
    set. Passing every parameter unconditionally therefore wiped
    ``end_time`` (making the entry open-ended) on every partial update;
    the #1764 parity suite caught it, and it is the same defect
    ``update_page`` was fixed for.

    The wipe-protection makes ``end_time=None`` mean "unchanged", which
    leaves no way to make a bounded entry open-ended again — the explicit
    ``clear_end_time=True`` flag is that escape hatch (#1873/#1874 review).
    ``clear_custom_days=True`` is the symmetric flag for dropping a stale
    custom day list when switching ``day_pattern`` away from ``custom``.
    REST is unaffected: its PATCH body distinguishes absent from null
    natively.
    """
    try:
        from src.schedules.models import ScheduleUpdate
        from src.schedules.service import get_schedule_service

        svc = get_schedule_service()
        fields: dict[str, Any] = {}
        if page_id is not None:
            fields["page_id"] = page_id
        if start_time is not None:
            fields["start_time"] = start_time
        if end_time is not None:
            fields["end_time"] = end_time
        if clear_end_time:
            fields["end_time"] = None
        if day_pattern is not None:
            fields["day_pattern"] = day_pattern
        if enabled is not None:
            fields["enabled"] = enabled
        if custom_days is not None:
            fields["custom_days"] = custom_days
        if clear_custom_days:
            fields["custom_days"] = None
        # No empty-fields guard: an empty ScheduleUpdate is a no-op merge, and
        # the pre-#1764 tool always called the service — the "not found" reply
        # for an unknown id (pinned by tests/test_mcp_server.py) depends on it.

        entry = svc.update_schedule(schedule_id, ScheduleUpdate(**fields))
        if entry is None:
            return err(f"Schedule '{schedule_id}' not found.")
        return ok(f"Schedule '{schedule_id}' updated.", schedule_id=entry.id)
    except Exception as exc:
        return err(f"Error updating schedule '{schedule_id}': {exc}")


def delete_schedule(schedule_id: str) -> dict[str, Any]:
    """Delete a schedule entry permanently."""
    try:
        from src.schedules.service import get_schedule_service

        svc = get_schedule_service()
        # #1742: delete_schedule() returns False when the id does not exist.
        if not svc.delete_schedule(schedule_id):
            return err(f"Schedule '{schedule_id}' not found.")
        return ok(f"Schedule '{schedule_id}' deleted successfully.", schedule_id=schedule_id)
    except Exception as exc:
        return err(f"Error deleting schedule '{schedule_id}': {exc}")


def set_schedule_mode(enabled: bool, board_id: str | None = None) -> dict[str, Any]:
    """Enable or disable schedule-based display.

    Schedule mode is a settings flag (per-board since #1244), not
    something ScheduleService owns — same mixup as issue #1559.

    ``board_id`` targets that board's flag (#1765); omitted keeps the
    legacy primary-board call. An unknown board is an error here because
    ``SettingsService.set_schedule_enabled`` logs-and-no-ops on one, which
    over MCP would read as success while changing nothing.
    """
    try:
        from src.settings.service import get_settings_service

        svc = get_settings_service()
        if board_id is not None:
            boards = svc.get_board_settings().boards or []
            if not any(isinstance(b, dict) and b.get("id") == board_id for b in boards):
                return err(f"Board not found: {board_id}")
            svc.set_schedule_enabled(enabled, board_id=board_id)
        else:
            svc.set_schedule_enabled(enabled)
        state = "enabled" if enabled else "disabled"
        target = f" for board '{board_id}'" if board_id is not None else ""
        return ok(f"Schedule mode {state}{target}.", enabled=enabled, board_id=board_id)
    except Exception as exc:
        return err(f"Error setting schedule mode: {exc}")


# ---------------------------------------------------------------------------
# Collection operations
# ---------------------------------------------------------------------------


def create_collection(
    name: str,
    page_ids: list[str],
    selection_mode: str = "time",
    interval_seconds: int = 30,
    rules: list[dict[str, str]] | None = None,
    default_page_id: str | None = None,
    poll_seconds: int = 10,
) -> dict[str, Any]:
    """Create a collection that decides which page to show."""
    try:
        from src.collections.models import (
            CollectionCreate,
            TimeModeConfig,
            VariableModeConfig,
            VariableRule,
        )
        from src.collections.service import get_collection_service

        svc = get_collection_service()

        time_cfg = TimeModeConfig(interval_seconds=interval_seconds)
        variable_cfg: Any = None
        if selection_mode == "variable":
            if not default_page_id:
                return err("variable mode requires default_page_id")
            variable_cfg = VariableModeConfig(
                rules=[VariableRule(**r) for r in (rules or [])],
                default_page_id=default_page_id,
                poll_seconds=poll_seconds,
            )

        data = CollectionCreate(
            name=name,
            page_ids=page_ids,
            selection_mode=selection_mode,  # type: ignore[arg-type]
            time=time_cfg,
            variable=variable_cfg,
        )
        collection = svc.create_collection(data)
        return ok(
            f"Collection '{name}' created with {len(page_ids)} pages in {selection_mode} mode.",
            collection_id=collection.id,
            name=collection.name,
        )
    except Exception as exc:
        return err(f"Error creating collection: {exc}")


def update_collection(
    collection_id: str,
    name: str | None = None,
    page_ids: list[str] | None = None,
    selection_mode: str | None = None,
    interval_seconds: int | None = None,
    rules: list[dict[str, str]] | None = None,
    default_page_id: str | None = None,
    poll_seconds: int | None = None,
) -> dict[str, Any]:
    """Update a collection's name, page list, or selection config.

    An interval-only update changes the time-mode config without forcing
    ``selection_mode`` back to ``"time"`` — flipping a variable-mode
    collection requires sending ``selection_mode`` explicitly.
    """
    try:
        from src.collections.models import (
            CollectionUpdate,
            TimeModeConfig,
            VariableModeConfig,
            VariableRule,
        )
        from src.collections.service import get_collection_service

        svc = get_collection_service()

        time_cfg: Any = TimeModeConfig(interval_seconds=interval_seconds) if interval_seconds is not None else None
        variable_cfg: Any = None
        if rules is not None or default_page_id is not None or poll_seconds is not None:
            if not default_page_id:
                return err("variable mode update requires default_page_id")
            variable_cfg = VariableModeConfig(
                rules=[VariableRule(**r) for r in (rules or [])],
                default_page_id=default_page_id,
                poll_seconds=poll_seconds if poll_seconds is not None else 10,
            )

        data = CollectionUpdate(
            name=name,
            page_ids=page_ids,
            selection_mode=selection_mode,  # type: ignore[arg-type]
            time=time_cfg,
            variable=variable_cfg,
        )
        collection = svc.update_collection(collection_id, data)
        if collection is None:
            return err(f"Collection '{collection_id}' not found.")
        return ok(f"Collection '{collection_id}' updated.", collection_id=collection.id)
    except Exception as exc:
        return err(f"Error updating collection '{collection_id}': {exc}")


def delete_collection(collection_id: str) -> dict[str, Any]:
    """Delete a collection permanently."""
    try:
        from src.collections.service import get_collection_service

        svc = get_collection_service()
        # #1742: same as delete_schedule above — the boolean was dropped.
        if not svc.delete_collection(collection_id):
            return err(f"Collection '{collection_id}' not found.")
        return ok(
            f"Collection '{collection_id}' deleted successfully.",
            collection_id=collection_id,
        )
    except Exception as exc:
        return err(f"Error deleting collection '{collection_id}': {exc}")


# ---------------------------------------------------------------------------
# Settings / system operations (chat-grammar surface)
# ---------------------------------------------------------------------------


async def update_setting(category: str, values: dict[str, Any]) -> dict[str, Any]:
    """Change a non-credential system setting.

    Chat-grammar op. Each category delegates to the REST handler that owns
    it (the same endpoints the web drawer calls), so validation and
    normalization live exactly once. ``active_page`` resolves to the
    canonical :func:`set_active_page` executor shared with MCP.
    """
    from fastapi import HTTPException

    try:
        if category == "active_page":
            page_id = values.get("page_id")
            if not isinstance(page_id, str) or not page_id:
                return err("active_page requires values.page_id")
            return await set_active_page(page_id)

        import src.api_server as api

        if category == "display":
            await api.update_display_settings(dict(values))
        elif category == "transitions":
            await api.update_transition_settings(dict(values))
        elif category == "output":
            await api.update_output_settings(dict(values))
        elif category == "polling":
            await api.update_polling_settings(dict(values))
        elif category == "location":
            await api.update_location_settings(dict(values))
        elif category == "silence_schedule":
            await api.update_silence_schedule(api.SilenceScheduleRequest(**values))
        else:
            return err(f"Unknown setting category: {category!r}")
    except HTTPException as exc:
        return err(f"Error updating {category} settings: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error updating {category} settings: {exc}")

    return ok(f"{category} settings updated.", category=category)


async def trigger_system_update() -> dict[str, Any]:
    """Trigger an in-place system update via the updater sidecar.

    Chat-grammar op. Delegates to the system router's apply handler
    (#1758) — the process may be recreated shortly after it succeeds.
    """
    from fastapi import HTTPException

    try:
        from src.system.routes import system_update_apply

        response = await system_update_apply()
    except HTTPException as exc:
        return err(f"Error triggering system update: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error triggering system update: {exc}")

    return ok("System update started. The board will restart shortly.", detail=serialize(response))
