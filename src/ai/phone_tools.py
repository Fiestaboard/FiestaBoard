"""FiestaBot from a phone (H21b): a default-deny tool and op allow-list.

A phone's ``control`` credential reaches ``POST /pages/ai/chat`` and
``POST /ai/operations``. Both run tools in-process with the hub's full power,
so the phone's limits have to hold *inside* them, not only at the route:

* **One table, keyed on the credential.** :data:`CONTROL_TOOLS` names a tier
  for every MCP tool (``src/mcp_server.py``), every chat-only tool and every
  operation in ``src/ops/registry.py`` (canonical names; chat spellings map
  onto them). A name with no row is **denied**. The tier follows the tier of
  the tool's REST equivalent for a phone (``src/auth/scopes.py``). The caller
  is identified by the scope the auth middleware resolved, never by anything
  the client sends.
* **Checked when a call runs.** :class:`PhoneToolBackend` wraps the chat's
  tool backend: fresh calls *and* calls resumed from a client-sent transcript
  go through :meth:`PhoneToolBackend.call_tool`, which re-checks the tier,
  the argument rules and, for tier 2, the step-up elevation at that moment.
  The offered catalogue is filtered too, so the model does not plan with
  tools it cannot use.
* **Tier 2 always pauses.** Tier-2 tools are re-described as needing
  approval, and the chat route ignores ``approval_mode`` and the
  conversation's "don't ask again" for phones, so nothing tier 2 runs without
  an Approve on the phone *and* a live step-up.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from typing import Any, Literal

from src.auth import phone_policy
from src.auth.step_up import STEP_UP_REQUIRED

from .mcp_bridge import ToolBackend, ToolDescriptor, ToolOutcome

Tier = Literal["allowed", "step_up", "denied"]

ALLOWED: Tier = "allowed"
STEP_UP: Tier = "step_up"
DENIED: Tier = "denied"

# The phone's REST surface already covers these (pages, schedules, collections,
# overrides, installed-plugin configuration, TVs, status and diagnostics), or
# they are tier 1 there (update checks; testing a saved AI provider by id).
_ALLOWED = (
    # Chat-only and client-side (the web UI applies them; no server effect).
    "ask_user",
    "replace_page",
    "apply_patch",
    "suggest_variables",
    "navigate_to_page",
    "navigate_to_schedule",
    "update_task_list",
    # Pages.
    "list_pages",
    "get_page",
    "create_page",
    "update_page",
    "delete_page",
    "render_page_preview",
    "preview_saved_page",
    "validate_template",
    "list_formula_functions",
    "export_page",
    "list_staff_picks",
    "get_current_display",
    "get_template_variables",
    "set_active_page",
    "get_active_page",
    # Schedules and collections.
    "list_schedules",
    "validate_schedules",
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    "set_default_page",
    "set_schedule_mode",
    "list_collections",
    "create_collection",
    "update_collection",
    "delete_collection",
    # What the displays show.
    "get_board_content",
    "send_message",
    "get_temporary_override",
    "set_temporary_override",
    "cancel_temporary_override",
    "force_refresh",
    "get_silence_status",
    "pause_board",
    "resume_board",
    "identify_tile",
    # TVs.
    "list_panels",
    "create_panel",
    "update_panel",
    "delete_panel",
    # Installed plugins: read, enable, configure (secrets stay masked).
    "list_installed_plugins",
    "list_registry_plugins",
    "enable_plugin",
    "disable_plugin",
    "configure_plugin",
    "list_plugin_instances",
    "create_plugin_instance",
    "delete_plugin_instance",
    "list_plugin_options",
    "get_plugin_manifest",
    "list_plugin_errors",
    "get_plugin_data",
    # Tier 1: read-like checks.
    "list_pending_plugin_updates",
    "check_plugin_updates",
    "check_for_update",
    "test_ai_provider",
    # Displays: read-only descriptions (secrets masked), and H21a's add, change,
    # remove and detect-size. A connection change that echoes a masked key is
    # refused for phones (see _DISPLAY_CONNECTION_TOOLS).
    "list_display_outputs",
    "get_display_info",
    "add_board",
    "remove_board",
    "detect_board_size",
    "update_board",  # not its host or mode: see the argument rule
    "create_display",
    # Status and diagnostics.
    "get_system_status",
    "run_network_diagnostics",
)

# Tier 2: an Approve on the phone and a live step-up when the call runs.
_STEP_UP = (
    "install_plugin",  # registry only: see the argument rule below
    "uninstall_plugin",
    "update_plugin",
    "update_all_plugins",
    "update_setting",
    "trigger_system_update",
    "restart_system",
    "shutdown_system",
    "disconnect_wifi",
    "forget_wifi_network",
    "export_backup",  # redacted for a phone
)

# Denied for phones, named so the table is complete. Importing pages saves them (the
# phone only previews an import). The rest are debug tools, demo pages and a
# settings summary whose routes a phone cannot reach.
_DENIED = (
    # Merges connection settings and keeps omitted secrets; a phone changes a
    # display's connection through PUT /settings/board, which checks re-entry.
    "configure_display",
    # Device actions can carry temporary connection edits; until the output
    # side of the H10 F5 host guard ships, the chat does not add a new path to them.
    "run_display_action",
    "import_page",
    "import_staff_pick",
    "get_settings_summary",
    "blank_board",
    "fill_board",
    "show_board_debug_info",
    "clear_board_cache",
    "get_plugin_demo_page",
    "create_plugin_demo_page",
)

CONTROL_TOOLS: dict[str, Tier] = {
    **dict.fromkeys(_ALLOWED, ALLOWED),
    **dict.fromkeys(_STEP_UP, STEP_UP),
    **dict.fromkeys(_DENIED, DENIED),
}

#: Arguments that make an otherwise permitted call a denied one.
_GIT_INSTALL_ARGS = ("repository", "branch")

#: ``update_board`` arguments that change where a display's key is sent (H21a).
_BOARD_CONNECTION_ARGS = ("host", "api_mode")

#: ``update_setting`` categories a phone may change (tier 2). The others stay
#: with the web app: ``mqtt`` (a host change would send the stored password to
#: the new host), ``ai`` (the REST route enforces key re-entry instead), the
#: release channel and automatic updates, and anything not listed.
PHONE_SETTING_CATEGORIES = frozenset(
    {
        "active_page",
        "display",
        "transitions",
        "output",
        "polling",
        "location",
        "silence_schedule",
        "schedule_behavior",
        "general",
    }
)


def tier_for(name: str, args: dict[str, Any] | None = None) -> Tier:
    """The phone's tier for calling *name* with *args*. Unknown names are denied."""
    tier = CONTROL_TOOLS.get(name, DENIED)
    if name == "install_plugin" and any((args or {}).get(key) for key in _GIT_INSTALL_ARGS):
        # Install from a Git URL runs arbitrary code; it stays browser-only.
        return DENIED
    if name == "update_setting" and (args or {}).get("category") not in PHONE_SETTING_CATEGORIES:
        return DENIED
    if name == "update_board" and any(key in (args or {}) for key in _BOARD_CONNECTION_ARGS):
        # The tool takes no key, so a host or mode change would keep the stored
        # one and send it to the new host. A phone uses PUT /settings/board.
        return DENIED
    return tier


def denied_message(name: str) -> str:
    return f"{name} isn't available from the phone app. Use the web app for it."


STEP_UP_MESSAGE = f"{STEP_UP_REQUIRED}: enter your password on this phone, then approve again."


class PhoneToolBackend:
    """The chat's tool backend as a phone may use it.

    *is_elevated* is asked on every tier-2 call, at the moment it would run,
    because a step-up can lapse in the middle of a conversation.
    """

    def __init__(self, inner: ToolBackend, is_elevated: Callable[[], bool]) -> None:
        self._inner = inner
        self._is_elevated = is_elevated

    async def list_tools(self) -> list[ToolDescriptor]:
        offered = []
        for descriptor in await self._inner.list_tools():
            tier = CONTROL_TOOLS.get(descriptor.name, DENIED)
            if tier == DENIED:
                continue
            if tier == STEP_UP:
                # Whatever its annotations say, a tier-2 tool pauses for an Approve.
                descriptor = dataclasses.replace(descriptor, destructive=True, read_only=False)
            offered.append(descriptor)
        return offered

    async def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        tier = tier_for(name, args)
        if tier == DENIED:
            message = denied_message(name)
            return ToolOutcome(
                status="blocked", error=message, result={"status": "blocked", "code": "forbidden", "message": message}
            )
        if tier == STEP_UP and not self._is_elevated():
            return ToolOutcome(
                status="blocked",
                error=STEP_UP_MESSAGE,
                result={"status": "blocked", "code": STEP_UP_REQUIRED, "message": STEP_UP_MESSAGE},
            )
        outcome = await self._inner.call_tool(name, args)
        if name == "export_backup" and outcome.status == "ok" and isinstance(outcome.result, dict):
            outcome = dataclasses.replace(outcome, result=phone_policy.redact_backup(outcome.result))
        return outcome


__all__ = [
    "ALLOWED",
    "CONTROL_TOOLS",
    "DENIED",
    "STEP_UP",
    "STEP_UP_MESSAGE",
    "PhoneToolBackend",
    "denied_message",
    "tier_for",
]
