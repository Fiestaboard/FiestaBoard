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


def _plugin_strategy_refusal(transition_strategy: str | None) -> dict[str, Any] | None:
    """The REST layer's beta gate on ``plugin:<id>`` strategies, as an envelope.

    ``POST/PUT /pages`` and ``POST /pages/import`` all refuse a plugin
    transition while ``beta.transition_plugins_enabled`` is off, so a page
    can never store a strategy the runtime will not honor. The same guard
    is reused here rather than re-derived, so the three page writers and
    their MCP counterparts cannot disagree about it.
    """
    from fastapi import HTTPException

    from src.pages.routes import _reject_plugin_strategy_when_beta_off

    try:
        _reject_plugin_strategy_when_beta_off(transition_strategy)
    except HTTPException as exc:
        return err(rest_detail(exc))
    return None


def create_page(
    name: str,
    template_lines: list[str],
    device_type: str = "flagship",
    duration_seconds: int = 300,
    line_metadata: list[dict[str, Any]] | None = None,
    notes_wide: int | None = None,
    notes_tall: int | None = None,
    transition_strategy: str | None = None,
    transition_interval_ms: int | None = None,
    transition_step_size: int | None = None,
) -> dict[str, Any]:
    """Create a new template page with every field the page editor saves.

    ``notes_wide``/``notes_tall`` size a ``note_array`` page; ``line_metadata``
    is the per-line alignment + wrap the editor stores; the three
    ``transition_*`` fields are the per-page override of the system
    transition. Omitted fields take the model defaults, exactly like a REST
    ``POST /pages`` body that leaves them out.
    """
    try:
        from src.pages.models import PageCreate
        from src.pages.service import get_page_service

        refusal = _plugin_strategy_refusal(transition_strategy)
        if refusal is not None:
            return refusal

        svc = get_page_service()
        fields: dict[str, Any] = {
            "name": name,
            "type": "template",
            "device_type": device_type,
            "template": template_lines,
            "duration_seconds": duration_seconds,
        }
        supplied = {
            "line_metadata": line_metadata,
            "notes_wide": notes_wide,
            "notes_tall": notes_tall,
            "transition_strategy": transition_strategy,
            "transition_interval_ms": transition_interval_ms,
            "transition_step_size": transition_step_size,
        }
        fields.update({key: value for key, value in supplied.items() if value is not None})
        page = svc.create_page(PageCreate(**fields))
        return ok(
            f"Page '{name}' created with id '{page.id}'.",
            page_id=page.id,
            name=page.name,
            device_type=page.device_type,
        )
    except Exception as exc:
        return err(f"Error creating page: {exc}")


def update_page(
    page_id: str,
    name: str | None = None,
    template_lines: list[str] | None = None,
    duration_seconds: int | None = None,
    device_type: str | None = None,
    notes_wide: int | None = None,
    notes_tall: int | None = None,
    line_metadata: list[dict[str, Any]] | None = None,
    transition_strategy: str | None = None,
    transition_interval_ms: int | None = None,
    transition_step_size: int | None = None,
    clear_transition_override: bool = False,
) -> dict[str, Any]:
    """Update any of the fields the page editor saves. Only supplied fields change.

    Only fields the caller actually supplied are passed through —
    ``PageService.update_page`` merges with ``model_dump(exclude_unset=True)``,
    where an explicit ``None`` counts as set and would wipe the template.

    That wipe-protection makes ``transition_strategy=None`` mean "unchanged",
    which leaves no way to drop a per-page transition override and fall back
    to the system default — ``clear_transition_override=True`` is that
    escape hatch (the ``clear_end_time`` pattern from :func:`update_schedule`).

    A device or size retarget (``device_type``/``notes_wide``/``notes_tall``)
    answers ``incompatible_references`` exactly as ``PUT /pages/{id}`` does:
    the schedule entries, per-board active pages and silence pages that now
    point this page at a board it no longer fits. Warn-only — nothing is
    mutated — so the caller must relay the list rather than a bare success.
    """
    try:
        from src.devices import size_key
        from src.pages.models import PageUpdate
        from src.pages.service import find_incompatible_references, get_page_service

        refusal = _plugin_strategy_refusal(transition_strategy)
        if refusal is not None:
            return refusal

        svc = get_page_service()
        supplied = {
            "name": name,
            "template": template_lines,
            "duration_seconds": duration_seconds,
            "device_type": device_type,
            "notes_wide": notes_wide,
            "notes_tall": notes_tall,
            "line_metadata": line_metadata,
            "transition_strategy": transition_strategy,
            "transition_interval_ms": transition_interval_ms,
            "transition_step_size": transition_step_size,
        }
        fields: dict[str, Any] = {key: value for key, value in supplied.items() if value is not None}
        if clear_transition_override:
            # Explicit Nones: PageStorage.update lets exactly these three be
            # cleared back to "inherit the system transition" (#1306).
            fields.update(transition_strategy=None, transition_interval_ms=None, transition_step_size=None)
        if not fields:
            return err(
                "Nothing to update: pass at least one of name, template_lines, duration_seconds, "
                "device_type, notes_wide, notes_tall, line_metadata, transition_strategy, "
                "transition_interval_ms, transition_step_size, or clear_transition_override."
            )

        existing = svc.get_page(page_id)
        page = svc.update_page(page_id, PageUpdate(**fields))
        if page is None:
            return err(f"Page '{page_id}' not found.")

        incompatible: list[dict[str, Any]] = []
        if existing is not None:
            old_size = size_key(existing.device_type, existing.notes_wide, existing.notes_tall)
            new_size = size_key(page.device_type, page.notes_wide, page.notes_tall)
            if old_size != new_size:
                incompatible = find_incompatible_references(page)

        message = f"Page '{page_id}' updated."
        if incompatible:
            message += (
                f" The retarget left {len(incompatible)} reference(s) pointing this page at a board it no longer"
                " fits — see incompatible_references."
            )
        return ok(
            message,
            page_id=page.id,
            name=page.name,
            device_type=page.device_type,
            incompatible_references=serialize(incompatible),
        )
    except Exception as exc:
        return err(f"Error updating page '{page_id}': {exc}")


def import_page(share_string: str) -> dict[str, Any]:
    """Create a page from a share string — ``POST /pages/import``.

    The same three verdicts as the REST handler: a string the decoder rejects
    or that does not satisfy ``PageCreate`` is the caller's problem, a page
    the service refuses is reported with its reason, and the beta gate on
    ``plugin:<id>`` strategies applies exactly as it does on create.
    """
    try:
        from src.pages.models import PageCreate
        from src.pages.service import get_page_service
        from src.pages.share import decode_page

        try:
            page_data = decode_page(share_string)
        except ValueError as exc:
            return err(str(exc))
        try:
            page_create = PageCreate(**{k: v for k, v in page_data.items() if k in PageCreate.model_fields})
        except Exception as exc:
            return err(f"Invalid share string — {exc}")

        refusal = _plugin_strategy_refusal(page_create.transition_strategy)
        if refusal is not None:
            return refusal

        page = get_page_service().create_page(page_create)
        return ok(
            f"Page '{page.name}' imported with id '{page.id}'.",
            page_id=page.id,
            name=page.name,
            device_type=page.device_type,
        )
    except Exception as exc:
        return err(f"Error importing page: {exc}")


def import_staff_pick(pick_id: str) -> dict[str, Any]:
    """Import a curated staff pick — ``GET /staff-picks/{id}/share`` then import.

    The catalog is the checked-in ``staff-picks/picks.json`` the REST router
    serves; its loader is reused so the two surfaces read the same file.
    """
    try:
        # The catalog loader lives beside the router that serves it; there
        # is no staff-picks service (the catalog is a static file).
        from src.staff_picks.routes import _load_staff_picks

        pick = next((p for p in _load_staff_picks() if isinstance(p, dict) and p.get("id") == pick_id), None)
        if pick is None:
            return err(f"Staff pick not found: {pick_id}")

        result = import_page(pick.get("share_string") or "")
        if result.get("status") != "success":
            return result
        return ok(
            f"Staff pick '{pick.get('name', pick_id)}' imported as page '{result['page_id']}'.",
            page_id=result["page_id"],
            name=result["name"],
            device_type=result["device_type"],
            pick_id=pick_id,
            required_plugins=serialize(pick.get("required_plugins") or []),
        )
    except Exception as exc:
        return err(f"Error importing staff pick '{pick_id}': {exc}")


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
# Transition Lab operations (beta)
#
# Both delegate to :mod:`src.transitions.service`, the domain layer behind
# ``POST /transitions/test-live`` and ``POST /transitions/restore``. The
# service raises ``TransitionError`` with the status/detail pair the router
# answers; here a 409 (silence window, paused board) becomes the same
# ``status: "blocked"`` policy envelope :func:`send_message` returns, and
# everything else is an error.
# ---------------------------------------------------------------------------


def _transition_beta_refusal() -> dict[str, Any] | None:
    """The router's beta gate, as an envelope: 404 while the flag is off."""
    from src.settings.service import get_settings_service

    if get_settings_service().get_beta_settings().transition_plugins_enabled:
        return None
    return err("Transition plugins are an experimental beta. Enable them in Settings → Beta to use this tool.")


def _transition_refusal(exc: Any, board_id: str | None) -> dict[str, Any]:
    """Map a ``TransitionError`` onto the executor envelope contract."""
    detail = str(getattr(exc, "detail", exc))
    if getattr(exc, "status_code", None) == 409:
        paused = "paused" in detail.lower()
        return {
            "status": "blocked",
            "message": detail,
            "paused": paused,
            "silence_mode": not paused,
            "board_id": board_id,
        }
    return err(detail)


async def test_transition_live(
    plugin_id: str,
    to_page_id: str,
    from_page_id: str | None = None,
    config: dict[str, Any] | None = None,
    board_id: str | None = None,
) -> dict[str, Any]:
    """Run a transition plugin once on the real board — ``POST /transitions/test-live``."""
    from fastapi import HTTPException

    refusal = _transition_beta_refusal()
    if refusal is not None:
        return refusal
    try:
        from src.transitions import service as transitions
        from src.transitions.models import TransitionLiveTestRequest

        response = await transitions.run_live_transition_test(
            TransitionLiveTestRequest(
                plugin_id=plugin_id,
                to_page_id=to_page_id,
                from_page_id=from_page_id,
                config=config,
                board_id=board_id,
            )
        )
    except transitions.TransitionError as exc:
        return _transition_refusal(exc, board_id)
    except HTTPException as exc:
        # _require_board still raises the transport error for an unknown board.
        return err(f"Error running live transition test: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error running live transition test: {exc}")

    target = f" on board '{board_id}'" if board_id is not None else ""
    return ok(
        f"Transition '{plugin_id}' ran{target}; the board is now showing page '{to_page_id}'. "
        "Call restore_board() to return it to its active page.",
        sent=bool(response.sent),
        plugin_id=response.plugin_id,
        from_page_id=response.from_page_id,
        to_page_id=response.to_page_id,
        board_id=response.board_id,
    )


async def restore_board(board_id: str | None = None) -> dict[str, Any]:
    """Snap a board back to its active page — ``POST /transitions/restore``."""
    from fastapi import HTTPException

    refusal = _transition_beta_refusal()
    if refusal is not None:
        return refusal
    try:
        from src.transitions import service as transitions
        from src.transitions.models import TransitionRestoreRequest

        response = await transitions.restore_after_transition_test(TransitionRestoreRequest(board_id=board_id))
    except transitions.TransitionError as exc:
        return _transition_refusal(exc, board_id)
    except HTTPException as exc:
        return err(f"Error restoring the board: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error restoring the board: {exc}")

    target = f"Board '{board_id}'" if board_id is not None else "The board"
    return ok(
        f"{target} is back on its active page '{response.page_id}'.",
        page_id=response.page_id,
        sent=bool(response.sent),
        board_id=response.board_id,
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

        import src.settings.models as models
        import src.settings.routes as api

        # The handlers take Pydantic request models since the Phase 2
        # conventions pass; build the model here rather than handing them a
        # dict. ValidationError is caught by the generic handler below and
        # reported to the chat op like any other bad input.
        if category == "display":
            await api.update_display_settings(models.DisplaySettingsUpdate(**values))
        elif category == "transitions":
            await api.update_transition_settings(models.TransitionSettingsUpdate(**values))
        elif category == "output":
            await api.update_output_settings(models.OutputSettingsUpdate(**values))
        elif category == "polling":
            await api.update_polling_settings(models.PollingSettingsUpdate(**values))
        elif category == "location":
            await api.update_location_settings(models.LocationSettingsUpdate(**values))
        elif category == "silence_schedule":
            await api.update_silence_schedule(models.SilenceScheduleRequest(**values))
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
