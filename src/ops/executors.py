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
  ``config.json``, and only the service writes both. Since Phase 2 slice 4
  that service raises :class:`src.plugins.errors.PluginError`, not a
  transport exception, so the executors below catch the domain error and
  flatten it with :func:`~src.ops.results.plugin_detail`.

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

from src.plugins.errors import PluginError

from .results import err, ok, plugin_detail, rest_detail, serialize

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
    try:
        await _plugin_service().install_from_registry(plugin_id)
    except PluginError as exc:
        return err(f"Error installing plugin '{plugin_id}': {plugin_detail(exc)}")
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
    try:
        _plugin_service().enable_plugin(plugin_id)
    except PluginError as exc:
        return err(f"Error enabling plugin '{plugin_id}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error enabling plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' enabled successfully.", plugin_id=plugin_id)


def disable_plugin(plugin_id: str) -> dict[str, Any]:
    """Disable an installed plugin without uninstalling it."""
    try:
        _plugin_service().disable_plugin(plugin_id)
    except PluginError as exc:
        return err(f"Error disabling plugin '{plugin_id}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error disabling plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' disabled successfully.", plugin_id=plugin_id)


def uninstall_plugin(plugin_id: str) -> dict[str, Any]:
    """Permanently remove an installed plugin. Irreversible."""
    try:
        _plugin_service().uninstall(plugin_id)
    except PluginError as exc:
        return err(f"Error uninstalling plugin '{plugin_id}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error uninstalling plugin '{plugin_id}': {exc}")

    return ok(f"Plugin '{plugin_id}' uninstalled successfully.", plugin_id=plugin_id)


def configure_plugin(plugin_id: str, config: dict[str, Any]) -> dict[str, Any]:
    """Merge the given keys into the plugin's stored config and persist.

    Merge — not replace — so a partial update never drops previously-set
    fields (and never trips required-field validation on the keys it did
    not send). Pinned by tests/test_mcp_state_effects.py.
    """
    from src.config_manager import get_config_manager

    try:
        # Raw STORED config, WITHOUT the env-var overlay — this merge is
        # persisted, and merging the overlay in would write env secrets
        # into config.json (issue #1761 / #1864 review).
        existing = get_config_manager().get_plugin_config(plugin_id, include_env_overrides=False) or {}
        merged = {**existing, **config}
        masked = _plugin_service().update_plugin_config(plugin_id, merged)
    except PluginError as exc:
        return err(f"Error configuring plugin '{plugin_id}': {plugin_detail(exc)}")
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
    try:
        await _plugin_service().apply_update(plugin_id)
    except PluginError as exc:
        return err(f"Error updating plugin '{plugin_id}': {plugin_detail(exc)}")
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

    from src.settings.models import SetActivePageRequest
    from src.settings.routes import set_active_page as _rest_set_active_page

    body: dict[str, Any] = {"page_id": page_id}
    if board_id is not None:
        body["board_id"] = board_id
    try:
        response = await _rest_set_active_page(SetActivePageRequest(**body))
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


class _SendTarget:
    """The collaborators one board write needs, resolved once.

    Built by :func:`_resolve_send_target`, which is the gate sequence
    ``POST /send-message`` performs before it touches a board. Factored out
    of :func:`send_message` so :func:`send_characters` cannot drift from it:
    the two operations differ only in what grid they hand the client.
    """

    __slots__ = ("board", "board_id", "client", "primary_id", "service", "settings_service")

    def __init__(self, service, client, board, board_id, primary_id, settings_service) -> None:
        self.service = service
        self.client = client
        self.board = board
        self.board_id = board_id
        self.primary_id = primary_id
        self.settings_service = settings_service


def _resolve_send_target(board_id: str | None) -> tuple[_SendTarget | None, dict[str, Any] | None]:
    """``(target, refusal)`` — exactly one of the two is not ``None``.

    The refusal is already an executor envelope: an ``err`` for a missing
    collaborator, or a ``status: "blocked"`` result for the silence window
    (#1788) and a paused board (#970). Blocked is deliberately not an error —
    it is policy, and a model relaying it should not retry.
    """
    # get_service is the DisplayService singleton accessor — api_server
    # owns it, but this is the same seam get_system_status and
    # set_active_page already use; no REST handler is called.
    from src.api_server import get_service
    from src.config import Config
    from src.settings.service import get_settings_service

    service = get_service()
    if not service:
        return None, err("Display service not initialized.")

    settings_service = get_settings_service()
    primary_id = settings_service.get_primary_board_id()
    board: dict[str, Any] | None = None
    if board_id is not None:
        boards = settings_service.get_board_settings().boards or []
        board = next((b for b in boards if isinstance(b, dict) and b.get("id") == board_id), None)
        if board is None:
            return None, err(f"Board not found: {board_id}")

    # Silence gate (#1788): resolve the *target* board's window; omitted
    # board_id resolves the primary, exactly like the REST handler.
    if Config.is_silence_mode_active(board_id if board_id is not None else primary_id):
        return None, {
            "status": "blocked",
            "message": "Manual sends blocked during silence mode to prevent wake-ups",
            "silence_mode": True,
            "board_id": board_id,
        }

    # Pause gate (#970): a paused board is left untouched.
    if settings_service.is_paused(board_id=board_id) is True:
        return None, {
            "status": "blocked",
            "message": "Board is paused — sends are blocked until it is resumed.",
            "paused": True,
            "board_id": board_id,
        }

    client = service.get_board_client(board_id) if board_id is not None else service.vb_client
    if not client:
        return None, err(
            f"Board client not initialized: {board_id}" if board_id is not None else "Board client not initialized."
        )

    # Size the grid to the target board (the REST handler's active-first-
    # board sizing when board_id is omitted).
    if board is None:
        board_settings = settings_service.get_board_settings()
        board = board_settings.boards[0] if board_settings.boards else {}

    return _SendTarget(service, client, board, board_id, primary_id, settings_service), None


def _target_dimensions(target: _SendTarget):
    """Rows/cols of the board this send targets."""
    from src.devices import resolve_dimensions

    return resolve_dimensions(
        target.board.get("device_type") or "flagship",
        target.board.get("notes_wide") or 1,
        target.board.get("notes_tall") or 1,
    )


def _transition_for(target: _SendTarget, strategy, step_interval_ms, step_size):
    """Per-call transition overrides, falling back to the stored settings.

    ``None`` means "use what the install is configured for" — the behavior
    every caller had before the overrides existed.
    """
    stored = target.settings_service.get_transition_settings()
    return (
        stored.strategy if strategy is None else strategy,
        stored.step_interval_ms if step_interval_ms is None else step_interval_ms,
        stored.step_size if step_size is None else step_size,
    )


def _after_send(target: _SendTarget) -> None:
    """Out-of-band bookkeeping every manual write owes the rest of the app.

    The board now shows content the display loop didn't put there
    (#1794/#1831): mark it, push fresh MQTT state so Home Assistant agrees,
    and ask for an adaptive refresh. The dedupe cache is deliberately left
    alone so the message survives the next engine tick.
    """
    try:
        target.service.mark_showing_out_of_band(target.board_id)
    except Exception as exc:
        logger.debug("Out-of-band mark after send failed: %s", exc)
    try:
        from src.mqtt import get_mqtt_client

        mqtt_client = get_mqtt_client()
        publisher = getattr(mqtt_client, "_state_publisher", None) if mqtt_client else None
        if publisher is not None:
            publisher.mark_display_updated()
            publisher.gather_and_publish()
    except Exception as exc:
        logger.debug("MQTT state publish after send failed: %s", exc)
    # Adaptive post-send refresh is primary-only (board-state polling
    # tracks only the primary board — issue #1243).
    if target.board_id is None or target.board_id == target.primary_id:
        try:
            target.service.request_board_refresh()
        except Exception as exc:
            logger.debug("Board refresh after send failed: %s", exc)


def send_message(
    text: str,
    board_id: str | None = None,
    *,
    strategy: str | None = None,
    step_interval_ms: int | None = None,
    step_size: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Send an ad-hoc text message straight to a board (issue #1765).

    Mirrors ``POST /send-message`` gate for gate — silence (#1788), pause
    (#970), out-of-band bookkeeping and MQTT state push (#1794/#1831),
    adaptive refresh — through the same service seams, and shares the
    wrap/convert/render core (:mod:`src.displays.messages`) with the REST
    handler so the two surfaces render identically. On top of the REST
    behavior it can target a secondary board via ``board_id``.

    Silence and pause come back as ``status: "blocked"`` results, not
    errors — they are deliberate policy, and the model should relay them
    rather than retry.

    The keyword-only arguments are pass-throughs for the ``/v1`` front door
    (``POST /v1/boards/{board}/message``): a per-request transition, and
    ``force`` to bypass the client's unchanged-content dedupe. Every one of
    them defaults to the behavior this executor had before they existed —
    the stored transition settings, and no forcing.
    """
    try:
        from src.displays.messages import render_message

        target, refusal = _resolve_send_target(board_id)
        if refusal is not None:
            return refusal
        assert target is not None

        dims = _target_dimensions(target)
        resolved_strategy, resolved_interval, resolved_step = _transition_for(
            target, strategy, step_interval_ms, step_size
        )
        success, was_sent = render_message(
            target.client,
            text,
            rows=dims.rows,
            cols=dims.cols,
            strategy=resolved_strategy,
            step_interval_ms=resolved_interval,
            step_size=resolved_step,
            force=force,
        )
        if not success:
            return err("Failed to send message to the board.")
        if not was_sent:
            return ok("Message unchanged, no update needed.", skipped=True, board_id=board_id)

        _after_send(target)
        return ok("Message sent successfully.", board_id=board_id)
    except Exception as exc:
        return err(f"Error sending message: {exc}")


def send_characters(
    characters: list[list[int]],
    board_id: str | None = None,
    *,
    strategy: str | None = None,
    step_interval_ms: int | None = None,
    step_size: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Send an already-built flap grid to a board.

    The raw-grid sibling of :func:`send_message`: same gate sequence, same
    bookkeeping, no text layout. It backs the ``characters``, ``fill`` and
    ``page_id`` forms of ``POST /v1/boards/{board}/message``, which arrive as
    a grid rather than as a string, so those forms cannot acquire a different
    silence/pause/refresh story from the text form.

    ``characters`` is trusted to be the right shape for the target board —
    validating it is the caller's job, because the caller knows whether a
    mismatch is a client error (a supplied grid) or a server one (a page that
    rendered wrong).
    """
    try:
        target, refusal = _resolve_send_target(board_id)
        if refusal is not None:
            return refusal
        assert target is not None

        resolved_strategy, resolved_interval, resolved_step = _transition_for(
            target, strategy, step_interval_ms, step_size
        )
        success, was_sent = target.client.render(
            characters,
            strategy=resolved_strategy,
            step_interval_ms=resolved_interval,
            step_size=resolved_step,
            force=force,
        )
        if not success:
            return err("Failed to send characters to the board.")
        if not was_sent:
            return ok("Board content unchanged, no update needed.", skipped=True, board_id=board_id)

        _after_send(target)
        return ok("Characters sent successfully.", board_id=board_id)
    except Exception as exc:
        return err(f"Error sending characters: {exc}")


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
# Settings operations
#
# Each category delegates to the REST handler that owns it (the same
# endpoints the web Settings page calls), so validation and normalization
# live exactly once. Secrets are excluded by design: API keys, tokens,
# passwords and auth changes are entered in the web UI and never travel over
# MCP — reads mask them, and the writers below refuse them by name rather
# than silently dropping them.
# ---------------------------------------------------------------------------

#: Keys ``update_setting`` refuses in every category. Naming them (rather than
#: relying on the request model to ignore unknown keys) is what turns a model
#: "helpfully" pasting a password into a clear refusal instead of a silent
#: no-op that reports success.
SECRET_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "password",
        "username",
        "headers",
        "token",
        "local_api_key",
        "cloud_key",
        "note_array_token",
        "client_secret",
    }
)

#: ``general`` keys the Settings page edits. The stored block also carries
#: legacy copies of the polling interval and output target, which have their
#: own categories, so the writer is narrowed to what the UI actually offers.
GENERAL_SETTING_KEYS: tuple[str, ...] = ("instance_name", "timezone", "time_format", "date_format", "welcome_message")

#: Non-secret fields of an AI provider entry. ``api_key`` and ``headers`` are
#: secrets; anything else is unknown to the provider model.
AI_PROVIDER_PUBLIC_KEYS: tuple[str, ...] = ("id", "name", "protocol", "base_url", "models", "default_model")

#: The MQTT keys the tool accepts, in the request model's spelling.
MQTT_SETTING_KEYS: tuple[str, ...] = ("enabled", "broker_host", "broker_port", "external_url")

#: Spellings the MQTT category also accepts for the broker address.
_MQTT_KEY_ALIASES = {"host": "broker_host", "port": "broker_port"}


def _refuse_secret_keys(category: str, keys: Any) -> dict[str, Any] | None:
    """An error envelope naming the first secret key in ``keys``, or ``None``."""
    for key in keys:
        if key in SECRET_SETTING_KEYS:
            return err(
                f"'{key}' is a credential and cannot be set through this tool. "
                f"Ask the user to enter it in the web UI (Settings → {category})."
            )
    return None


def _refuse_unknown_keys(category: str, keys: Any, allowed: Any) -> dict[str, Any] | None:
    """An error envelope listing keys ``category`` does not accept, or ``None``.

    The request models ignore unknown keys, so without this check a typo
    (``{"hostname": ...}``) would be reported as a successful update that
    changed nothing.
    """
    unknown = sorted(set(keys) - set(allowed))
    if unknown:
        return err(f"Unknown keys for category '{category}': {', '.join(unknown)}. Valid keys: {', '.join(allowed)}.")
    return None


def _prepare_ai_values(values: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Validate the ``ai`` category and shape it for ``PUT /settings/ai``.

    Provider entries are the tricky part: the endpoint REPLACES the provider
    list, and it keeps a provider's stored key only when the incoming entry
    carries the mask placeholder. So every provider the caller sends gets
    ``api_key="***"`` when it already exists (key preserved) and ``""`` when
    it is new (a key-less provider the user completes in the web UI).

    Returns ``(body, None)`` or ``(None, error_envelope)``.
    """
    body = dict(values)
    providers = body.get("providers")
    if providers is None:
        return body, None
    if not isinstance(providers, list):
        return None, err("'providers' must be a list of provider objects.")

    from src.config_manager import get_config_manager

    existing_ids = {
        p.get("id")
        for p in get_config_manager().get_ai_providers().get("providers", [])
        if isinstance(p, dict) and p.get("id")
    }
    cleaned: list[dict[str, Any]] = []
    for raw in providers:
        if not isinstance(raw, dict) or not raw.get("id"):
            return None, err("Each provider must be an object with at least an 'id'.")
        refusal = _refuse_secret_keys("AI", raw) or _refuse_unknown_keys("ai.providers[]", raw, AI_PROVIDER_PUBLIC_KEYS)
        if refusal is not None:
            return None, refusal
        provider = dict(raw)
        provider["api_key"] = "***" if provider["id"] in existing_ids else ""
        cleaned.append(provider)
    body["providers"] = cleaned
    return body, None


async def update_setting(category: str, values: dict[str, Any]) -> dict[str, Any]:
    """Change one category of non-credential settings.

    Each category delegates to the REST handler that owns it (the same
    endpoints the web Settings page calls), so validation and normalization
    live exactly once. ``active_page`` resolves to the canonical
    :func:`set_active_page` executor shared with MCP.

    Unknown keys are refused rather than ignored, and secret keys are refused
    by name — see :data:`SECRET_SETTING_KEYS`.
    """
    from fastapi import HTTPException

    try:
        if category == "active_page":
            page_id = values.get("page_id")
            if not isinstance(page_id, str) or not page_id:
                return err("active_page requires values.page_id")
            return await set_active_page(page_id, board_id=values.get("board_id"))

        refusal = _refuse_secret_keys(category, values)
        if refusal is not None:
            return refusal

        import src.settings.models as models
        import src.settings.routes as api

        # The handlers take Pydantic request models since the Phase 2
        # conventions pass; build the model here rather than handing them a
        # dict. ValidationError is caught by the generic handler below and
        # reported to the caller like any other bad input. Every branch
        # refuses unknown keys first — the models ignore extras, which would
        # otherwise report a typo as a successful update.
        body: dict[str, Any] = values
        if category == "display":
            allowed: Any = models.DisplaySettingsUpdate.model_fields
            handler: Any = lambda: api.update_display_settings(models.DisplaySettingsUpdate(**body))  # noqa: E731
        elif category == "transitions":
            allowed = models.TransitionSettingsUpdate.model_fields
            handler = lambda: api.update_transition_settings(models.TransitionSettingsUpdate(**body))  # noqa: E731
        elif category == "output":
            allowed = models.OutputSettingsUpdate.model_fields
            handler = lambda: api.update_output_settings(models.OutputSettingsUpdate(**body))  # noqa: E731
        elif category == "polling":
            allowed = models.PollingSettingsUpdate.model_fields
            handler = lambda: api.update_polling_settings(models.PollingSettingsUpdate(**body))  # noqa: E731
        elif category == "location":
            allowed = models.LocationSettingsUpdate.model_fields
            handler = lambda: api.update_location_settings(models.LocationSettingsUpdate(**body))  # noqa: E731
        elif category == "silence_schedule":
            allowed = models.SilenceScheduleRequest.model_fields
            handler = lambda: api.update_silence_schedule(models.SilenceScheduleRequest(**body))  # noqa: E731
        elif category == "general":
            from src.config_api.models import GeneralConfigUpdate
            from src.config_api.routes import update_general_config

            allowed = GENERAL_SETTING_KEYS
            handler = lambda: update_general_config(GeneralConfigUpdate(**body))  # noqa: E731
        elif category == "beta":
            allowed = models.BetaSettingsUpdate.model_fields
            handler = lambda: api.update_beta_settings(models.BetaSettingsUpdate(**body))  # noqa: E731
        elif category == "plugins":
            allowed = models.PluginSettingsUpdate.model_fields
            handler = lambda: api.update_plugin_settings(models.PluginSettingsUpdate(**body))  # noqa: E731
        elif category == "mqtt":
            body = {_MQTT_KEY_ALIASES.get(k, k): v for k, v in values.items()}
            allowed = MQTT_SETTING_KEYS
            handler = lambda: api.update_mqtt_settings(models.MqttSettingsUpdate(**body))  # noqa: E731
        elif category == "ai":
            allowed = models.AiProvidersUpdate.model_fields
            handler = lambda: api.update_ai_settings(models.AiProvidersUpdate(**body))  # noqa: E731
        elif category == "release_channel":
            from src.system.models import ReleaseChannelRequest
            from src.system.routes import set_release_channel

            allowed = ("channel",)
            handler = lambda: set_release_channel(ReleaseChannelRequest(**body))  # noqa: E731
        elif category == "auto_update":
            from src.system.models import AutoUpdateRequest
            from src.system.routes import system_update_set_auto

            allowed = ("interval",)
            handler = lambda: system_update_set_auto(AutoUpdateRequest(**body))  # noqa: E731
        elif category == "hdmi_kiosk":
            allowed = models.HdmiKioskRequest.model_fields
            handler = lambda: api.set_hdmi_kiosk(models.HdmiKioskRequest(**body))  # noqa: E731
        else:
            return err(f"Unknown setting category: {category!r}")

        refusal = _refuse_unknown_keys(category, body, allowed)
        if refusal is not None:
            return refusal
        if category == "ai":
            prepared, refusal = _prepare_ai_values(values)
            if refusal is not None:
                return refusal
            body = prepared or {}
        await handler()
    except HTTPException as exc:
        return err(f"Error updating {category} settings: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error updating {category} settings: {exc}")

    return ok(f"{category} settings updated.", category=category)


# ---------------------------------------------------------------------------
# Board hardware operations
#
# Per-board, non-secret fields only. Credentials (local API key, cloud key,
# note-array token, per-tile keys) are never accepted or returned; the
# settings service preserves the stored ones because the roster handed back
# to ``PUT /settings/board`` is the raw stored one, not a masked copy.
# ---------------------------------------------------------------------------

#: The projection of a board every board tool returns. Never the raw dict —
#: that carries credentials. ``host`` is write-only (``update_board`` sets
#: it, ``has_host`` confirms it), matching the summary tool's projection.
BOARD_PUBLIC_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "device_type",
    "notes_wide",
    "notes_tall",
    "board_color",
    "code62_glyph",
    "api_mode",
    "enabled",
    "paused",
    "schedule_enabled",
)


def board_public_view(board: dict[str, Any]) -> dict[str, Any]:
    """Credential-free projection of a stored board dict."""
    view = {key: board.get(key) for key in BOARD_PUBLIC_FIELDS}
    view["has_host"] = bool(board.get("host"))
    view["has_credentials"] = bool(
        board.get("local_api_key") or board.get("cloud_key") or board.get("note_array_token")
    )
    return view


def _stored_boards() -> list[dict[str, Any]]:
    from src.settings.service import get_settings_service

    return [b for b in (get_settings_service().get_board_settings().boards or []) if isinstance(b, dict)]


def _validate_board_fields(**fields: Any) -> dict[str, Any] | None:
    """Refuse values ``BoardInstance`` would silently coerce to a default.

    ``BoardInstance.__post_init__`` rewrites an unknown device_type,
    board_color, code62_glyph or api_mode to its default instead of failing
    — over MCP that would read as "updated" while the board kept its old
    value. A malformed host raises the guard's own HTTPException(400).
    """
    from src.board_guards import validate_board_host
    from src.devices import CODE62_GLYPHS, DEVICE_TYPES, MAX_NOTES_PER_AXIS, VALID_API_MODES

    vocab = {
        "device_type": DEVICE_TYPES,
        "board_color": ("black", "white"),
        "code62_glyph": CODE62_GLYPHS,
        "api_mode": VALID_API_MODES,
    }
    for key, allowed in vocab.items():
        value = fields.get(key)
        if value is not None and value not in allowed:
            return err(f"{key} must be one of: {', '.join(allowed)} (got {value!r}).")
    for key in ("notes_wide", "notes_tall"):
        value = fields.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= MAX_NOTES_PER_AXIS:
            return err(f"{key} must be an integer between 1 and {MAX_NOTES_PER_AXIS}.")
    host = fields.get("host")
    if host is not None:
        validate_board_host(host)
    return None


async def update_board(
    board_id: str,
    name: str | None = None,
    device_type: str | None = None,
    notes_wide: int | None = None,
    notes_tall: int | None = None,
    board_color: str | None = None,
    code62_glyph: str | None = None,
    api_mode: str | None = None,
    host: str | None = None,
) -> dict[str, Any]:
    """Change non-secret hardware fields of one board.

    The Settings page edits a board by re-sending the whole roster to
    ``PUT /settings/board`` with one entry changed; this does the same, so
    the service-side normalization (name trimming, ``board_type`` sync,
    masked-credential preservation) and the client rebuild happen exactly
    as they do for the UI.
    """
    from fastapi import HTTPException

    try:
        import src.settings.models as models
        import src.settings.routes as api

        updates = {
            key: value
            for key, value in {
                "name": name,
                "device_type": device_type,
                "notes_wide": notes_wide,
                "notes_tall": notes_tall,
                "board_color": board_color,
                "code62_glyph": code62_glyph,
                "api_mode": api_mode,
                "host": host,
            }.items()
            if value is not None
        }
        if not updates:
            return err(
                "Nothing to update: pass at least one of name, device_type, notes_wide, notes_tall, "
                "board_color, code62_glyph, api_mode, host."
            )
        refusal = _validate_board_fields(**updates)
        if refusal is not None:
            return refusal

        boards = [dict(b) for b in _stored_boards()]
        target = next((b for b in boards if b.get("id") == board_id), None)
        if target is None:
            return err(f"Board not found: {board_id}")
        target.update(updates)
        response = await api.update_board_settings(models.BoardSettingsUpdate(boards=boards))
    except HTTPException as exc:
        return err(f"Error updating board '{board_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error updating board '{board_id}': {exc}")

    stored = next((b for b in response.get("boards", []) if b.get("id") == board_id), target)
    return ok(f"Board '{board_id}' updated.", board_id=board_id, board=board_public_view(stored))


async def add_board(
    device_type: str,
    name: str | None = None,
    api_mode: str | None = None,
    notes_wide: int | None = None,
    notes_tall: int | None = None,
    board_color: str | None = None,
    host: str | None = None,
) -> dict[str, Any]:
    """Add a board to the roster (``POST /settings/board/add``).

    A board can be added without credentials — it appears in Settings →
    Boards where the user pastes the API key; until then it fails to
    initialize and says so in the boards summary.
    """
    from fastapi import HTTPException

    try:
        import src.settings.models as models
        import src.settings.routes as api

        body = {
            key: value
            for key, value in {
                "device_type": device_type,
                "name": name,
                "api_mode": api_mode,
                "notes_wide": notes_wide,
                "notes_tall": notes_tall,
                "board_color": board_color,
                "host": host,
            }.items()
            if value is not None
        }
        refusal = _validate_board_fields(**body)
        if refusal is not None:
            return refusal
        before = {b.get("id") for b in _stored_boards()}
        response = await api.add_board_instance(models.AddBoardRequest(**body))
    except HTTPException as exc:
        return err(f"Error adding board: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error adding board: {exc}")

    added = next((b for b in response.get("boards", []) if b.get("id") not in before), None)
    if added is None:  # pragma: no cover - the handler appends or raises
        return err("Board was not added.")
    return ok(
        f"Board '{added.get('name')}' added with id '{added.get('id')}'.",
        board_id=added.get("id"),
        board=board_public_view(added),
    )


async def remove_board(board_id: str) -> dict[str, Any]:
    """Remove a board from the roster (``DELETE /settings/board/{id}``).

    The handler refuses the last board and a board a FiestaPanel still
    drives (delete the panel instead); both come back as errors here.
    """
    from fastapi import HTTPException

    try:
        import src.settings.routes as api

        response = await api.remove_board_instance(board_id)
    except HTTPException as exc:
        return err(f"Error removing board '{board_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error removing board '{board_id}': {exc}")

    remaining = [b.get("id") for b in response.get("boards", []) if isinstance(b, dict)]
    return ok(f"Board '{board_id}' removed.", board_id=board_id, remaining_board_ids=remaining)


async def detect_board_size(board_id: str) -> dict[str, Any]:
    """Read a board's live layout and classify its device type and grid."""
    from fastapi import HTTPException

    try:
        import src.settings.routes as api

        detected = await api.detect_board_size(board_id)
    except HTTPException as exc:
        return err(f"Error detecting size of board '{board_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error detecting size of board '{board_id}': {exc}")

    return {"board_id": board_id, **serialize(detected)}


async def identify_tile(
    board_id: str, row: int | None = None, col: int | None = None, target: str = "tile"
) -> dict[str, Any]:
    """Flash slot positions onto a local note array's tiles.

    Only the saved-tile form of ``POST /settings/board/{id}/identify`` —
    the unsaved-credential override the assign dialog uses needs a tile API
    key, which never travels over MCP.
    """
    from fastapi import HTTPException

    try:
        import src.settings.models as models
        import src.settings.routes as api

        response = await api.identify_board_tiles(
            board_id, models.BoardIdentifyRequest(target=target, row=row, col=col)
        )
    except HTTPException as exc:
        return err(f"Error identifying tiles on board '{board_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error identifying tiles on board '{board_id}': {exc}")

    results = serialize(response).get("results", [])
    flashed = sum(1 for r in results if r.get("success"))
    return ok(
        f"Identify pattern sent to {flashed} of {len(results)} tile(s); "
        "the real frame returns on the next display cycle.",
        board_id=board_id,
        results=results,
    )


# ---------------------------------------------------------------------------
# FiestaPanel operations (``/panels``)
# ---------------------------------------------------------------------------


async def create_panel(
    name: str,
    screen_diagonal_inches: float = 55.0,
    screen_aspect_w: float = 16.0,
    screen_aspect_h: float = 9.0,
) -> dict[str, Any]:
    """Create a FiestaPanel and its auto-fit virtual board."""
    from fastapi import HTTPException

    try:
        from src.panels.models import PanelCreate
        from src.panels.routes import create_panel as _rest_create_panel

        panel = await _rest_create_panel(
            PanelCreate(
                name=name,
                screen_diagonal_inches=screen_diagonal_inches,
                screen_aspect_w=screen_aspect_w,
                screen_aspect_h=screen_aspect_h,
            )
        )
    except HTTPException as exc:
        return err(f"Error creating panel: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error creating panel: {exc}")

    data = serialize(panel)
    return ok(
        f"Panel '{name}' created with id '{data.get('id')}' on virtual board '{data.get('board_id')}'.",
        panel_id=data.get("id"),
        board_id=data.get("board_id"),
        panel=data,
    )


async def update_panel(
    panel_id: str,
    name: str | None = None,
    screen_diagonal_inches: float | None = None,
    screen_aspect_w: float | None = None,
    screen_aspect_h: float | None = None,
    calibration_scale: float | None = None,
    animations_enabled: bool | None = None,
    is_display: bool | None = None,
    backdrop: str | None = None,
    auto_dim: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update a panel's display configuration. Only supplied fields change."""
    from fastapi import HTTPException

    try:
        from src.panels.models import PanelUpdate
        from src.panels.routes import update_panel as _rest_update_panel

        fields = {
            key: value
            for key, value in {
                "name": name,
                "screen_diagonal_inches": screen_diagonal_inches,
                "screen_aspect_w": screen_aspect_w,
                "screen_aspect_h": screen_aspect_h,
                "calibration_scale": calibration_scale,
                "animations_enabled": animations_enabled,
                "is_display": is_display,
                "backdrop": backdrop,
                "auto_dim": auto_dim,
            }.items()
            if value is not None
        }
        if not fields:
            return err(
                "Nothing to update: pass at least one of name, screen_diagonal_inches, screen_aspect_w, "
                "screen_aspect_h, calibration_scale, animations_enabled, is_display, backdrop, auto_dim."
            )
        panel = await _rest_update_panel(panel_id, PanelUpdate(**fields))
    except HTTPException as exc:
        return err(f"Error updating panel '{panel_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error updating panel '{panel_id}': {exc}")

    return ok(f"Panel '{panel_id}' updated.", panel_id=panel_id, panel=serialize(panel))


async def delete_panel(panel_id: str) -> dict[str, Any]:
    """Delete a panel and its virtual board."""
    from fastapi import HTTPException

    try:
        from src.panels.routes import delete_panel as _rest_delete_panel

        await _rest_delete_panel(panel_id)
    except HTTPException as exc:
        return err(f"Error deleting panel '{panel_id}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error deleting panel '{panel_id}': {exc}")

    return ok(f"Panel '{panel_id}' deleted along with its virtual board.", panel_id=panel_id)


# ---------------------------------------------------------------------------
# Network operations (FiestaPi Wi-Fi). No scan/connect: joining a network
# needs a passphrase, which never travels over MCP.
# ---------------------------------------------------------------------------


async def disconnect_wifi() -> dict[str, Any]:
    """Bring the active Wi-Fi connection down (the saved profile is kept)."""
    from fastapi import HTTPException

    try:
        from src.network.routes import wifi_disconnect

        status = await wifi_disconnect()
    except HTTPException as exc:
        return err(f"Error disconnecting Wi-Fi: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error disconnecting Wi-Fi: {exc}")

    return ok("Wi-Fi disconnected. The saved profile is kept, so it may auto-join again.", status=serialize(status))


async def forget_wifi_network(name: str) -> dict[str, Any]:
    """Delete a saved Wi-Fi profile so the device stops auto-joining it."""
    from fastapi import HTTPException

    try:
        from src.network.routes import wifi_forget

        await wifi_forget(name)
    except HTTPException as exc:
        return err(f"Error forgetting Wi-Fi network '{name}': {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error forgetting Wi-Fi network '{name}': {exc}")

    return ok(f"Wi-Fi network '{name}' forgotten.", name=name)


# ---------------------------------------------------------------------------
# System operations (updater sidecar)
# ---------------------------------------------------------------------------


async def trigger_system_update() -> dict[str, Any]:
    """Trigger an in-place system update via the updater sidecar.

    Delegates to the system router's apply handler (#1758) — the process
    may be recreated shortly after it succeeds.
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


async def restart_system() -> dict[str, Any]:
    """Restart the FiestaBoard container via the updater sidecar."""
    from fastapi import HTTPException

    try:
        from src.system.routes import system_restart

        response = await system_restart()
    except HTTPException as exc:
        return err(f"Error restarting FiestaBoard: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error restarting FiestaBoard: {exc}")

    return ok(
        "Restart requested. The web UI drops for a few seconds while the container comes back.",
        detail=serialize(response),
    )


async def shutdown_system() -> dict[str, Any]:
    """Power the host off via the updater sidecar."""
    from fastapi import HTTPException

    try:
        from src.system.routes import system_shutdown

        response = await system_shutdown()
    except HTTPException as exc:
        return err(f"Error shutting down: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error shutting down: {exc}")

    return ok(
        "Shutdown requested. The host powers off and must be switched on again by hand.",
        detail=serialize(response),
    )


# ---------------------------------------------------------------------------
# Debug board actions (Settings → Advanced). Out-of-band writes to a board:
# the same gate sequence as send_message (silence, pause) through
# _resolve_send_target, then a forced raw send that bypasses the
# unchanged-content dedupe exactly like the /debug/* handlers do.
# ---------------------------------------------------------------------------


def _send_grid_out_of_band(
    board_id: str | None,
    build_grid: Any,
    *,
    success_message: str,
    failure_message: str,
    **extra: Any,
) -> dict[str, Any]:
    """Resolve the target board once, build a grid for its size, send it."""
    try:
        target, refusal = _resolve_send_target(board_id)
        if refusal is not None:
            return refusal
        assert target is not None

        dims = _target_dimensions(target)
        characters = build_grid(dims)
        success, was_sent = target.client.send_characters(characters, force=True)
        if not success:
            return err(failure_message)
        if not was_sent:
            # A forced send that still did not go out was dropped by the
            # client's send floor (#1868): the content was NOT delivered.
            return err(f"{failure_message}: the board accepts at most one message every few seconds — retry shortly.")
        _after_send(target)
        return ok(success_message, board_id=board_id, rows=dims.rows, cols=dims.cols, **extra)
    except Exception as exc:
        return err(f"{failure_message}: {exc}")


def blank_board(board_id: str | None = None) -> dict[str, Any]:
    """Clear a board by filling every tile with blank (code 0)."""
    return _send_grid_out_of_band(
        board_id,
        lambda dims: [[0] * dims.cols for _ in range(dims.rows)],
        success_message="Board blanked.",
        failure_message="Failed to blank the board",
    )


def fill_board(character_code: int, board_id: str | None = None) -> dict[str, Any]:
    """Fill every tile of a board with one flap code (0-71)."""
    if isinstance(character_code, bool) or not isinstance(character_code, int) or not 0 <= character_code <= 71:
        return err("character_code must be an integer flap code between 0 and 71.")
    return _send_grid_out_of_band(
        board_id,
        lambda dims: [[character_code] * dims.cols for _ in range(dims.rows)],
        success_message=f"Board filled with character code {character_code}.",
        failure_message="Failed to fill the board",
        character_code=character_code,
    )


def show_board_debug_info(board_id: str | None = None) -> dict[str, Any]:
    """Send the six-line support card (IPs, uptime, API mode, version) to a board."""

    def build(dims: Any) -> list[list[int]]:
        from src.debug.routes import _build_debug_text
        from src.text_to_board import text_to_board_array

        return text_to_board_array(_build_debug_text(), use_color_tiles=False, rows=dims.rows, cols=dims.cols)

    return _send_grid_out_of_band(
        board_id,
        build,
        success_message="Debug info card sent to the board (board IP, server IP, uptime, API mode, version, time).",
        failure_message="Failed to send the debug info card",
    )


def clear_board_cache(board_id: str | None = None) -> dict[str, Any]:
    """Drop a board client's unchanged-content cache so the next send always goes out."""
    try:
        from src.api_server import get_service
        from src.settings.service import get_settings_service

        service = get_service()
        if not service:
            return err("Display service not initialized.")
        if board_id is None:
            client = service.vb_client
        else:
            if not any(b.get("id") == board_id for b in _stored_boards()):
                return err(f"Board not found: {board_id}")
            client = service.get_board_client(board_id)
            if client is None and board_id == get_settings_service().get_primary_board_id():
                # Legacy installs key the primary runtime under a sentinel
                # (same fallback as get_board_content).
                client = service.vb_client
        if not client:
            return err(
                f"Board client not initialized: {board_id}" if board_id is not None else "Board client not initialized."
            )
        client.clear_cache()
    except Exception as exc:
        return err(f"Error clearing board cache: {exc}")

    return ok(
        "Cache cleared — the next send to this board goes out even if the content is unchanged.", board_id=board_id
    )
