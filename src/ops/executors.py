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
from src.send_outcome import SendOutcome

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
    plugin_id: str | None = None,
    auto_enable: bool = True,
    initial_config: dict[str, Any] | None = None,
    repository: str | None = None,
    branch: str = "",
) -> dict[str, Any]:
    """Install a plugin, optionally enable + configure it.

    Two sources, mirroring the Integrations page:

    - ``repository`` given — the "Add from Git" dialog
      (``POST /plugins/install``): clone that public git URL, on ``branch``
      when set; ``plugin_id`` is then an optional override of the id
      derived from the repository name.
    - only ``plugin_id`` — the registry install
      (``POST /plugins/registry/{id}/install``), unchanged.

    ``initial_config`` (chat grammar and MCP) is applied through
    :func:`configure_plugin` after a successful install.
    """
    if not repository and not plugin_id:
        return err("Nothing to install: pass plugin_id (registry install) or repository (git URL).")

    source = "git" if repository else "registry"
    label = plugin_id or repository
    try:
        if repository:
            plugin_id = await _plugin_service().install_from_git(repository, plugin_id=plugin_id, branch=branch)
        else:
            assert plugin_id is not None
            await _plugin_service().install_from_registry(plugin_id)
    except PluginError as exc:
        return err(f"Error installing plugin '{label}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error installing plugin '{label}': {exc}")

    if auto_enable:
        enabled = enable_plugin(plugin_id)
        if enabled.get("status") == "error":
            return err(f"Plugin '{plugin_id}' was installed but could not be enabled: {enabled['error']}")

    if initial_config:
        configured = configure_plugin(plugin_id, initial_config)
        if configured.get("status") == "error":
            return err(f"Plugin '{plugin_id}' was installed but could not be configured: {configured['error']}")

    state = "installed and enabled" if auto_enable else "installed (disabled)"
    origin = f" from {repository}" if repository else ""
    return ok(
        f"Plugin '{plugin_id}' {state} successfully{origin}.",
        plugin_id=plugin_id,
        enabled=auto_enable,
        source=source,
    )


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


async def check_plugin_updates() -> dict[str, Any]:
    """Run an immediate update check for every enabled external plugin.

    ``POST /plugins/updates/check``: a ``git ls-remote`` per plugin on a
    worker thread, refreshing the registry's cached status that
    ``list_pending_plugin_updates`` / ``update_all_plugins`` read.
    """
    import asyncio

    try:
        registry = _plugin_service().registry
        results = await asyncio.to_thread(registry.check_for_updates)
        blocked = registry.get_update_blocked_reasons()
    except Exception as exc:
        return err(f"Error checking for plugin updates: {exc}")

    available = sorted(pid for pid, has_update in results.items() if has_update)
    return ok(
        f"Checked {len(results)} plugin(s); {len(available)} update(s) available.",
        checked=len(results),
        updates_available=available,
        blocked=serialize(blocked),
    )


async def update_all_plugins() -> dict[str, Any]:
    """Fetch and reload every external plugin with a pending update.

    ``POST /plugins/updates/apply``: uses the cached status from the last
    check. Partial failure is a *success* envelope carrying ``failed`` —
    collapsing an N-plugin bulk update into one error would throw away
    which ones went through.
    """
    try:
        result = await _plugin_service().apply_all_updates()
    except PluginError as exc:
        return err(f"Error applying plugin updates: {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error applying plugin updates: {exc}")

    return ok(result["message"], updated=list(result["updated"]), failed=dict(result["failed"]))


def create_plugin_instance(plugin_id: str, label: str) -> dict[str, Any]:
    """Create a named instance of a multi-instance plugin.

    ``POST /plugins/{id}/instances``. The instance starts disabled with an
    empty config and is addressed everywhere else by its compound key
    ``base:label`` (label normalised to lowercase).
    """
    try:
        base_id, compound_key = _plugin_service().create_instance(plugin_id, label)
    except PluginError as exc:
        return err(f"Error creating instance '{label}' of plugin '{plugin_id}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error creating instance '{label}' of plugin '{plugin_id}': {exc}")

    instance_label = compound_key.split(":", 1)[1]
    return ok(
        f"Instance '{compound_key}' of plugin '{base_id}' created (disabled, unconfigured).",
        plugin_id=base_id,
        instance_label=instance_label,
        instance_key=compound_key,
    )


def delete_plugin_instance(plugin_id: str, label: str) -> dict[str, Any]:
    """Remove a plugin instance and purge its persisted config. Irreversible.

    ``DELETE /plugins/{id}/instances/{label}``. The base plugin is never
    touched.
    """
    try:
        base_id, compound_key = _plugin_service().delete_instance(plugin_id, label)
    except PluginError as exc:
        return err(f"Error deleting instance '{label}' of plugin '{plugin_id}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error deleting instance '{label}' of plugin '{plugin_id}': {exc}")

    return ok(
        f"Instance '{compound_key}' deleted.",
        plugin_id=base_id,
        instance_label=label,
        instance_key=compound_key,
    )


def create_plugin_demo_page(
    plugin_id: str,
    device_type: str | None = None,
    recreate: bool = False,
) -> dict[str, Any]:
    """Create the bundled demo page for a plugin.

    ``POST /plugins/{id}/demo-page``. REST always rebuilds the singleton;
    here ``recreate`` defaults to False so an assistant does not replace a
    demo page the user has since edited — an existing page is reported
    back with ``created=False`` instead.
    """
    try:
        result = _plugin_service().create_demo_page(plugin_id, device_type, recreate=recreate)
    except PluginError as exc:
        return err(f"Error creating demo page for plugin '{plugin_id}': {plugin_detail(exc)}")
    except Exception as exc:
        return err(f"Error creating demo page for plugin '{plugin_id}': {exc}")

    page = result["page"]
    if not result["created"]:
        message = (
            f"Demo page '{page.name}' for '{plugin_id}' already exists ({page.id}); "
            "pass recreate=True to rebuild it from the plugin's template."
        )
    elif result["recreated"]:
        message = f"Demo page '{page.name}' for '{plugin_id}' rebuilt with id '{page.id}'."
    else:
        message = f"Demo page '{page.name}' for '{plugin_id}' created with id '{page.id}'."
    return ok(
        message,
        page_id=page.id,
        name=page.name,
        device_type=result["device_type"],
        created=result["created"],
        recreated=result["recreated"],
    )


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


def _throttle_refusal(outcome: Any, board_id: str | None) -> dict[str, Any] | None:
    """The error envelope for a write the board's send floor dropped, or ``None``.

    The client reports a throttled write and an unchanged-content skip with
    the same ``(True, False)``, and they mean opposite things — after a skip
    the board shows the content, after a throttle it never left the process
    (#1794). ``outcome`` is the send's own :class:`SendOutcome` (returned
    with ``with_outcome=True``): the verdict decided under the send lock for
    THIS call. The first version of this gate read
    ``client.last_send_throttled`` after the call returned, and a concurrent
    engine tick or send worker on the same client could rewrite that flag
    in the gap — reporting a dropped write as ``skipped`` success, or an
    unchanged one as throttled (#1931 review).

    REST has answered the throttle with 429 + ``Retry-After`` since #1868;
    this executor reported it as ``skipped`` success, so an MCP model
    sending twice inside the window was told both landed (#1931).

    It is an *error*, not a ``status: "blocked"`` policy result: silence and
    pause are the user's standing instruction and a model should relay
    them, whereas a throttle is transient and the right move is to retry
    after the window. The retry hint — the REMAINING window, not the whole
    floor — rides in the text (the MCP error path has no header and no
    ``structuredContent``) and, for ``/v1``, as ``retry_after_seconds``.
    """
    from src.board_guards import throttle_retry_after, throttled_detail

    outcome = SendOutcome.of(outcome)
    retry_after = throttle_retry_after(outcome)
    if retry_after is None:
        return None
    return err(
        throttled_detail(retry_after, outcome.floor_seconds),
        retry_after_seconds=retry_after,
        board_id=board_id,
    )


def _settle_send(
    target: _SendTarget,
    outcome: Any,
    *,
    failure: str,
    success: str,
    unchanged: str | None = None,
    **fields: Any,
) -> dict[str, Any]:
    """Turn one board write's outcome into the executor's answer.

    The tail every board write in this module shares: a failed send is
    ``failure``; a write the send floor dropped is the throttle refusal;
    a write the client skipped as unchanged is ``unchanged`` reported as
    ``skipped`` success — or, when the caller forced the send and so has no
    unchanged case (``unchanged=None``), ``failure``; and a delivered write
    owes :func:`_after_send` its bookkeeping before reporting ``success``.
    """
    outcome = SendOutcome.of(outcome)
    if not outcome.success:
        return err(failure)
    if not outcome.was_sent:
        throttled = _throttle_refusal(outcome, target.board_id)
        if throttled is not None:
            return throttled
        if unchanged is None:
            return err(failure)
        return ok(unchanged, skipped=True, board_id=target.board_id)
    _after_send(target)
    return ok(success, board_id=target.board_id, **fields)


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
    (#970), the send-floor throttle (#1868/#1931), out-of-band bookkeeping
    and MQTT state push (#1794/#1831), adaptive refresh — through the same
    service seams, and shares the wrap/convert/render core
    (:mod:`src.displays.messages`) with the REST handler so the two surfaces
    render identically. On top of the REST behavior it can target a
    secondary board via ``board_id``.

    Silence and pause come back as ``status: "blocked"`` results, not
    errors — they are deliberate policy, and the model should relay them
    rather than retry. A write the board's send floor dropped is the
    opposite: an ``err`` envelope carrying the retry window (see
    :func:`_throttle_refusal`), because the content did not land and a
    retry after the window is exactly what should happen.

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
        outcome = render_message(
            target.client,
            text,
            rows=dims.rows,
            cols=dims.cols,
            strategy=resolved_strategy,
            step_interval_ms=resolved_interval,
            step_size=resolved_step,
            force=force,
            with_outcome=True,
        )
        return _settle_send(
            target,
            outcome,
            failure="Failed to send message to the board.",
            unchanged="Message unchanged, no update needed.",
            success="Message sent successfully.",
        )
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
        outcome = target.client.render(
            characters,
            strategy=resolved_strategy,
            step_interval_ms=resolved_interval,
            step_size=resolved_step,
            force=force,
            with_outcome=True,
        )
        return _settle_send(
            target,
            outcome,
            failure="Failed to send characters to the board.",
            unchanged="Board content unchanged, no update needed.",
            success="Characters sent successfully.",
        )
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


def _board_exists(settings_service: Any, board_id: str) -> bool:
    """Roster check shared by the board-scoped executors."""
    boards = settings_service.get_board_settings().boards or []
    return any(isinstance(b, dict) and b.get("id") == board_id for b in boards)


def _unknown_board(board_id: str | None) -> dict[str, Any] | None:
    """An ``err`` envelope when *board_id* names no configured board, else None.

    The schedule REST writes 404 on an unknown board (#1888) because the
    services below it would otherwise persist state parented to a board that
    does not exist and report success. ``None`` and ``""`` are the default
    board and pass through.
    """
    if not board_id:
        return None
    from src.settings.service import get_settings_service

    if not _board_exists(get_settings_service(), board_id):
        return err(f"Board not found: {board_id}")
    return None


def create_schedule(
    page_id: str,
    start_time: str,
    day_pattern: str = "all",
    end_time: str | None = None,
    enabled: bool = True,
    custom_days: list[str] | None = None,
    board_id: str | None = None,
    recurrence_type: str | None = None,
    annual_date: str | None = None,
    annual_end_date: str | None = None,
    one_off_date: str | None = None,
    one_off_end_date: str | None = None,
    start_type: str | None = None,
    start_sun_offset: int | None = None,
    end_type: str | None = None,
    end_sun_offset: int | None = None,
) -> dict[str, Any]:
    """Create a schedule entry showing a page (or collection) at a time slot.

    Every field the schedule form saves is accepted; the ones left ``None``
    take :class:`~src.schedules.models.ScheduleCreate`'s defaults (weekly
    recurrence, fixed times, the default board), so the pre-existing calls
    that send only the five core arguments are unchanged. An unknown
    ``board_id`` is refused up front, mirroring the REST 404 (#1888).
    """
    try:
        from src.schedules.models import ScheduleCreate
        from src.schedules.service import get_schedule_service

        refusal = _unknown_board(board_id)
        if refusal is not None:
            return refusal

        svc = get_schedule_service()
        fields: dict[str, Any] = {
            "page_id": page_id,
            "start_time": start_time,
            "end_time": end_time,
            "day_pattern": day_pattern,
            "enabled": enabled,
        }
        optional = {
            "custom_days": custom_days,
            "board_id": board_id,
            "recurrence_type": recurrence_type,
            "annual_date": annual_date,
            "annual_end_date": annual_end_date,
            "one_off_date": one_off_date,
            "one_off_end_date": one_off_end_date,
            "start_type": start_type,
            "start_sun_offset": start_sun_offset,
            "end_type": end_type,
            "end_sun_offset": end_sun_offset,
        }
        fields.update({k: v for k, v in optional.items() if v is not None})
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
    board_id: str | None = None,
    recurrence_type: str | None = None,
    annual_date: str | None = None,
    annual_end_date: str | None = None,
    one_off_date: str | None = None,
    one_off_end_date: str | None = None,
    start_type: str | None = None,
    start_sun_offset: int | None = None,
    end_type: str | None = None,
    end_sun_offset: int | None = None,
    clear_annual_end_date: bool = False,
    clear_one_off_end_date: bool = False,
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
    custom day list when switching ``day_pattern`` away from ``custom``,
    and ``clear_annual_end_date`` / ``clear_one_off_end_date`` do the same
    for the optional end of a date range. REST is unaffected: its PATCH
    body distinguishes absent from null natively.
    """
    try:
        from src.schedules.models import ScheduleUpdate
        from src.schedules.service import get_schedule_service

        refusal = _unknown_board(board_id)
        if refusal is not None:
            return refusal

        svc = get_schedule_service()
        supplied = {
            "page_id": page_id,
            "start_time": start_time,
            "end_time": end_time,
            "day_pattern": day_pattern,
            "enabled": enabled,
            "custom_days": custom_days,
            "board_id": board_id,
            "recurrence_type": recurrence_type,
            "annual_date": annual_date,
            "annual_end_date": annual_end_date,
            "one_off_date": one_off_date,
            "one_off_end_date": one_off_end_date,
            "start_type": start_type,
            "start_sun_offset": start_sun_offset,
            "end_type": end_type,
            "end_sun_offset": end_sun_offset,
        }
        fields: dict[str, Any] = {k: v for k, v in supplied.items() if v is not None}
        if clear_end_time:
            fields["end_time"] = None
        if clear_custom_days:
            fields["custom_days"] = None
        if clear_annual_end_date:
            fields["annual_end_date"] = None
        if clear_one_off_end_date:
            fields["one_off_end_date"] = None
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


def resolve_board_id(board_id: str | None) -> str | None:
    """The concrete board a board-scoped call targets.

    Omitted means the primary board — resolved to its real id, exactly as
    the ``/v1/boards/primary`` path segment resolves — so per-board state
    written here lands where the web UI (which always names the board) reads
    it back. ``None`` only when no board is configured at all.
    """
    from src.settings.service import get_settings_service

    if board_id:
        return board_id
    return get_settings_service().get_primary_board_id()


def set_default_page(page_id: str | None, board_id: str | None = None) -> dict[str, Any]:
    """Set (or with ``None`` clear) the page a board falls back to in schedule gaps.

    Mirrors ``PATCH /v1/boards/{board}`` with ``default_page_id``: the ref
    must name an existing page or collection, the board must exist, and the
    value is stored per board under the board's concrete id.
    """
    try:
        from src.collections.models import is_collection_id
        from src.collections.service import get_collection_service
        from src.pages.service import get_page_service
        from src.schedules.service import get_schedule_service

        refusal = _unknown_board(board_id)
        if refusal is not None:
            return refusal
        if page_id is not None:
            if is_collection_id(page_id):
                if not get_collection_service().get_collection(page_id):
                    return err(f"Collection not found: {page_id}")
            elif not get_page_service().get_page(page_id):
                return err(f"Page not found: {page_id}")

        target = resolve_board_id(board_id)
        get_schedule_service().set_default_page(page_id, board_id=target)
        if page_id is None:
            return ok("Default page cleared.", default_page_id=None, board_id=target)
        return ok(f"Default page set to '{page_id}'.", default_page_id=page_id, board_id=target)
    except Exception as exc:
        return err(f"Error setting default page: {exc}")


def _set_board_paused(paused: bool, board_id: str | None) -> dict[str, Any]:
    """Pause or resume a board (issue #970) — the ``paused`` half of ``PATCH /v1/boards``.

    While paused, nothing is written to the board from any code path. An
    unknown board is an error here because the REST route 404s before the
    setter runs, and a no-op reported as success is the #1888 defect.
    """
    try:
        from src.settings.service import get_settings_service

        refusal = _unknown_board(board_id)
        if refusal is not None:
            return refusal
        target = resolve_board_id(board_id)
        if target is None:
            return err("No board is configured on this install.")
        state = get_settings_service().set_paused(paused, board_id=target)
        verb = "paused" if state else "resumed"
        return ok(f"Board '{target}' {verb}.", paused=state, board_id=target)
    except Exception as exc:
        return err(f"Error {'pausing' if paused else 'resuming'} board: {exc}")


def pause_board(board_id: str | None = None) -> dict[str, Any]:
    """Stop every write to a board until :func:`resume_board`."""
    return _set_board_paused(True, board_id)


def resume_board(board_id: str | None = None) -> dict[str, Any]:
    """Let a paused board receive writes again."""
    return _set_board_paused(False, board_id)


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
    """Create a collection that decides which page to show.

    ``interval_seconds`` is the page duration for both ``time`` and
    ``random`` mode — the same number the collection form saves into
    whichever config block the chosen mode reads.
    """
    try:
        from src.collections.models import (
            CollectionCreate,
            RandomModeConfig,
            TimeModeConfig,
            VariableModeConfig,
            VariableRule,
        )
        from src.collections.service import get_collection_service

        svc = get_collection_service()

        time_cfg = TimeModeConfig(interval_seconds=interval_seconds)
        variable_cfg: Any = None
        random_cfg: Any = None
        if selection_mode == "variable":
            if not default_page_id:
                return err("variable mode requires default_page_id")
            variable_cfg = VariableModeConfig(
                rules=[VariableRule(**r) for r in (rules or [])],
                default_page_id=default_page_id,
                poll_seconds=poll_seconds,
            )
        elif selection_mode == "random":
            random_cfg = RandomModeConfig(interval_seconds=interval_seconds)

        data = CollectionCreate(
            name=name,
            page_ids=page_ids,
            selection_mode=selection_mode,  # type: ignore[arg-type]
            time=time_cfg,
            variable=variable_cfg,
            random=random_cfg,
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

    Mode-specific fields are MERGED with the stored config block, so a
    variable-mode collection can have only its ``poll_seconds`` or ``rules``
    changed without re-sending ``default_page_id``; the previous behavior
    demanded the whole block on every touch. An interval-only update changes
    the time-mode config without forcing ``selection_mode`` back to
    ``"time"`` — flipping a collection's mode requires sending
    ``selection_mode`` explicitly. In ``random`` mode ``interval_seconds``
    lands in the ``random`` block instead, the same way the form saves it.
    """
    try:
        from src.collections.models import (
            CollectionUpdate,
            RandomModeConfig,
            TimeModeConfig,
            VariableModeConfig,
            VariableRule,
        )
        from src.collections.service import get_collection_service

        svc = get_collection_service()
        existing = svc.get_collection(collection_id)
        if existing is None:
            return err(f"Collection '{collection_id}' not found.")

        effective_mode = selection_mode or existing.selection_mode
        time_cfg: Any = None
        random_cfg: Any = None
        if effective_mode == "random":
            # Switching to random needs a random block even without a new
            # interval (the model validator requires one); carry over the
            # duration the collection already rotates on.
            stored_random = existing.random.interval_seconds if existing.random else existing.time.interval_seconds
            random_cfg = RandomModeConfig(
                interval_seconds=interval_seconds if interval_seconds is not None else stored_random
            )
        elif interval_seconds is not None:
            time_cfg = TimeModeConfig(interval_seconds=interval_seconds)

        variable_cfg: Any = None
        touches_variable = rules is not None or default_page_id is not None or poll_seconds is not None
        if touches_variable or (effective_mode == "variable" and existing.variable is None):
            base = existing.variable
            merged_default = (
                default_page_id if default_page_id is not None else (base.default_page_id if base else None)
            )
            if not merged_default:
                return err("variable mode requires default_page_id")
            merged_rules: list[Any] = (
                [VariableRule(**r) for r in rules] if rules is not None else (list(base.rules) if base else [])
            )
            variable_cfg = VariableModeConfig(
                rules=merged_rules,
                default_page_id=merged_default,
                poll_seconds=poll_seconds if poll_seconds is not None else (base.poll_seconds if base else 10),
            )

        data = CollectionUpdate(
            name=name,
            page_ids=page_ids,
            selection_mode=selection_mode,  # type: ignore[arg-type]
            time=time_cfg,
            variable=variable_cfg,
            random=random_cfg,
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
    :func:`set_active_page` executor shared with MCP; ``schedule_behavior``
    is ``PUT /schedules/settings`` (the global ``defer_on_reenable`` toggle
    on the Schedules page).

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
        if category == "ai" and "approval_mode" in values:
            # #2021: the assistant must never loosen (or tighten) the policy
            # that decides whether its own destructive calls pause for the
            # user. Refused before the model is built, like a secret.
            return err(
                "'approval_mode' is the assistant's own approval policy and cannot be changed through "
                "this tool. Ask the user to switch it in the chat panel (Ask / Auto)."
            )

        if category == "schedule_behavior":
            from src.schedules.models import ScheduleBehaviorUpdate
            from src.schedules.routes import set_schedule_settings

            response = await set_schedule_settings(ScheduleBehaviorUpdate(**values))
            return ok(
                "schedule_behavior settings updated.",
                category=category,
                defer_on_reenable=response.defer_on_reenable,
            )

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
# Board state operations — the Home page's controls
#
# The temporary override and the forced resend are install-wide: the
# override lives in one consume-once store the display loop applies to the
# PRIMARY board only (src/main.py, "Temporary override (PRIMARY only)"), and
# POST /force-refresh clears every board's caches in one pass. Neither takes
# a board_id because neither REST route does; offering one would promise a
# targeting the store cannot honor.
# ---------------------------------------------------------------------------


async def set_temporary_override(
    page_id: str | None = None,
    template_lines: list[str] | None = None,
    line_metadata: list[dict[str, Any]] | None = None,
    device_type: str | None = None,
    notes_wide: int | None = None,
    notes_tall: int | None = None,
    duration_minutes: int | None = None,
    revert_mode: str = "schedule",
    revert_page_id: str | None = None,
) -> dict[str, Any]:
    """Show a saved page or a composed one-off on the primary board for a while.

    Delegates to ``POST /settings/temporary-override`` — the handler behind
    both the Home page's "force set" dialog (a saved page) and its compose
    dialog (inline lines, issue #1787) — so the exactly-one-of-page-or-
    template rule, the geometry checks and the 1–480 minute bound live once.
    ``duration_minutes=None`` is an indefinite override that stays until
    :func:`cancel_temporary_override`. Deliberately not gated by silence or
    pause: a user-initiated override beats the silence schedule (#949).
    """
    from fastapi import HTTPException

    from src.settings.models import TemporaryOverrideRequest
    from src.settings.routes import set_temporary_override as _rest_set_override

    try:
        request = TemporaryOverrideRequest(
            page_id=page_id,
            template=template_lines,
            line_metadata=line_metadata,
            device_type=device_type,
            notes_wide=notes_wide,
            notes_tall=notes_tall,
            duration_minutes=duration_minutes,
            revert_mode=revert_mode,
            revert_page_id=revert_page_id,
        )
        payload = await _rest_set_override(request)
    except HTTPException as exc:
        return err(f"Error setting temporary override: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error setting temporary override: {exc}")

    what = f"page '{page_id}'" if page_id else "a one-off message"
    how_long = f"for {duration_minutes} minutes" if duration_minutes is not None else "until cancelled"
    return ok(f"Temporary override set: {what} {how_long}.", override=serialize(payload))


async def cancel_temporary_override() -> dict[str, Any]:
    """Cancel the active temporary override and let the board revert.

    Delegates to ``DELETE /settings/temporary-override``: the ``page``
    revert mode is applied server-side and the display cache is cleared so
    the next tick re-renders. Cancelling when nothing is active is a no-op
    reported as success — the same answer the REST route gives.
    """
    from fastapi import HTTPException

    from src.settings.routes import clear_temporary_override as _rest_clear_override

    try:
        response = await _rest_clear_override()
    except HTTPException as exc:
        return err(f"Error cancelling temporary override: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error cancelling temporary override: {exc}")

    revert_mode = response.get("revert_mode") if isinstance(response, dict) else getattr(response, "revert_mode", None)
    if revert_mode is None:
        return ok("No temporary override was active.", was_active=False, revert_mode=None)
    return ok(f"Temporary override cancelled (revert mode: {revert_mode}).", was_active=True, revert_mode=revert_mode)


async def force_refresh() -> dict[str, Any]:
    """Resend the active content to every board, ignoring the unchanged-content caches.

    Delegates to ``POST /force-refresh`` — the Home page's "Resend to board"
    — which clears each board client's dedupe cache and the display loop's
    own per-runtime guard (#1794) before driving one send pass.
    """
    from fastapi import HTTPException

    from src.debug.routes import force_refresh as _rest_force_refresh

    try:
        response = await _rest_force_refresh()
    except HTTPException as exc:
        return err(f"Error forcing a refresh: {rest_detail(exc)}")
    except Exception as exc:
        return err(f"Error forcing a refresh: {exc}")

    sent = bool(getattr(response, "sent", False))
    message = "Display force-refreshed; content was resent to the board."
    if not sent:
        message = "Display refresh ran, but nothing was sent (UI-only output target, paused board, or no change)."
    return ok(message, sent=sent)


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
        # Forced, so there is no unchanged case: a ``(True, False)`` here is
        # the send floor dropping the write (#1868), and _settle_send answers
        # it with the same retry-window refusal send_message gives.
        outcome = target.client.send_characters(characters, force=True, with_outcome=True)
        return _settle_send(
            target,
            outcome,
            failure=failure_message,
            success=success_message,
            rows=dims.rows,
            cols=dims.cols,
            **extra,
        )
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
