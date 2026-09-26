"""The browser executes nothing; the server-side loop over MCP does.

Phase 2 Task 11 put ``POST /ai/operations`` between the drawer and the ops
layer so chat and MCP could not diverge. The agent-loop work removed the
browser from the execution path entirely: the drawer no longer posts
operations at all, and every tool the chat uses runs through the in-process
MCP server (``src/ai/mcp_bridge.py``).

What this file guards is the *structural* half of that: a future edit that
re-implements a tool in ``global-ai-chat-drawer.tsx`` — a REST call that
belongs to an executor, a ``handle<Op>`` callback, a return to the
operations endpoint — has to delete a test to land. Behaviour is covered end
to end in ``tests/test_ai_chat_e2e.py``.

Everything here reads the real TSX, so it fails on a rename rather than
passing vacuously — the last test proves the scans are looking at something.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAWER = REPO_ROOT / "web/src/components/global-ai-chat-drawer.tsx"
DRAWER_SOURCE = DRAWER.read_text(encoding="utf-8")
CHOREOGRAPHY_DIR = REPO_ROOT / "web/src/lib/ai-choreography"

#: REST client methods that existed only to execute a chat op in the browser.
#: Any of them reappearing in the drawer means an operation grew a second
#: implementation next to the MCP tool.
FORBIDDEN_DIRECT_API_CALLS = {
    "installRegistryPlugin",
    "enablePlugin",
    "disablePlugin",
    "uninstallPlugin",
    "updatePluginConfig",
    "updatePlugin",
    "createCollection",
    "updateCollection",
    "updateDisplaySettings",
    "updateTransitionSettings",
    "updateOutputSettings",
    "updatePollingSettings",
    "updateLocationSettings",
    "updateSilenceSchedule",
    "setActivePage",
    "applyUpdate",
    "createPage",
    "updatePage",
    "deletePage",
    "executeAiOperation",
}

#: The schedule mutations the drawer may still call directly, and why. The
#: MCP ``create_schedule`` has no ``start_type`` / ``*_sun_offset`` fields, so
#: restoring a deleted sunrise schedule through it would silently downgrade
#: it to a fixed clock time. Confined to the toast helper — asserted below.
UNDO_ONLY_API_CALLS = {"createSchedule", "updateSchedule", "deleteSchedule"}


def _api_calls(source: str) -> set[str]:
    return set(re.findall(r"\bapi\.([A-Za-z0-9_]+)\(", source))


def _toast_helper_source() -> str:
    start = DRAWER_SOURCE.index("const toastForToolResult = useCallback(")
    end = DRAWER_SOURCE.index("const invalidateFor = useCallback(")
    return DRAWER_SOURCE[start:end]


# ---------------------------------------------------------------------------
# The browser cannot re-grow an executor
# ---------------------------------------------------------------------------


def test_no_tool_has_a_browser_side_implementation():
    offenders = sorted(_api_calls(DRAWER_SOURCE) & FORBIDDEN_DIRECT_API_CALLS)
    assert offenders == [], (
        "global-ai-chat-drawer.tsx calls REST endpoints that belong to a tool. "
        "Tools run on the server through the MCP server; the browser only "
        f"observes the result. Offending calls: {offenders}"
    )


def test_the_operations_endpoint_is_gone_from_the_drawer():
    assert "executeAiOperation" not in DRAWER_SOURCE
    assert "/ai/operations" not in DRAWER_SOURCE


def test_no_handle_callback_survives_for_a_tool():
    """``const handleEnablePlugin = ...`` is the shape of the old dispatcher."""
    # The stream's lifecycle handlers are allowed: they are named for a
    # frame or a phase, never for a tool.
    lifecycle = {
        "ToolCall",
        "ToolStreaming",
        "ToolResult",
        "AwaitingApproval",
        "TurnComplete",
        "ConversationLoaded",
        "Stopped",
    }
    offenders = sorted(set(re.findall(r"const handle([A-Z][A-Za-z]+) = ", DRAWER_SOURCE)) - lifecycle)
    assert offenders == [], f"tools must not have their own browser handler: {offenders}"


def test_the_old_op_dispatch_is_gone():
    for relic in ("SERVER_EXECUTED_OPS", "chainAfter", "buildToolResultText", "switch (call.op)"):
        assert relic not in DRAWER_SOURCE, f"{relic} is back in the drawer"


def test_schedule_mutations_remain_confined_to_the_undo_affordances():
    """The three allowed direct calls exist only inside the toast helper."""
    helper = _toast_helper_source()
    outside = _api_calls(DRAWER_SOURCE.replace(helper, "")) & UNDO_ONLY_API_CALLS
    assert outside == set(), (
        "schedule REST mutations may only appear in toastForToolResult's Undo "
        f"actions; found {sorted(outside)} elsewhere in the drawer"
    )
    assert _api_calls(helper) & UNDO_ONLY_API_CALLS, "the Undo affordances disappeared from the toast helper"


def test_the_choreography_layer_makes_no_api_calls():
    """Narration is web-only and observes; it never executes."""
    offenders = []
    for path in CHOREOGRAPHY_DIR.rglob("*.ts"):
        if _api_calls(path.read_text(encoding="utf-8")):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"choreography files call the API: {offenders}"


# ---------------------------------------------------------------------------
# Guarding the guard
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# The cache keys the drawer invalidates must be keys something reads
# ---------------------------------------------------------------------------

QUERY_KEYS = REPO_ROOT / "web/src/lib/ai-choreography/query-keys.ts"
WEB_SOURCE_DIRS = (REPO_ROOT / "web/src", REPO_ROOT / "web/app")


def _declared_query_key_prefixes() -> set[str]:
    """Every ``["x"]`` / ``["x", "y"]`` literal in the choreography key map."""
    source = QUERY_KEYS.read_text(encoding="utf-8")
    return {m.group(1) for m in re.finditer(r'\[\s*"([^"]+)"', source)}


def _query_key_prefixes_in_use() -> set[str]:
    """The first element of every query key the web app declares.

    Literal ``queryKey: ["x", ...]`` sites, plus the board-scoped helpers in
    ``web/src/hooks/use-board.ts`` (``queryKeys.activePage()`` and friends
    build ``["activePage", boardId]`` and are what the board pages use).
    """
    used: set[str] = set()
    for root in WEB_SOURCE_DIRS:
        for path in root.rglob("*.ts*"):
            if path == QUERY_KEYS or "__tests__" in path.parts or path.name.endswith(".test.tsx"):
                continue
            used.update(re.findall(r'queryKey:\s*\[\s*"([^"]+)"', path.read_text(encoding="utf-8")))
    helpers = (REPO_ROOT / "web/src/hooks/use-board.ts").read_text(encoding="utf-8")
    start, end = (
        helpers.index("export const queryKeys = {"),
        helpers.index("};", helpers.index("export const queryKeys = {")),
    )
    used.update(re.findall(r'\[\s*"([^"]+)"', helpers[start:end]))
    return used


def test_every_invalidated_query_key_is_one_a_component_reads():
    """An invalidation for a key nothing subscribes to refreshes nothing.

    The old drawer carried ``boardCurrentMessage`` (the real key is
    ``board-current-message``) and per-category settings keys no card ever
    used, so ``send_message`` never refreshed the board. The map is checked
    against the queries actually declared in the app.
    """
    declared = _declared_query_key_prefixes()
    used = _query_key_prefixes_in_use()
    assert declared, "the key map scan found nothing"
    assert used, "the app scan found no queries"
    unknown = sorted(declared - used)
    assert unknown == [], f"query-keys.ts invalidates keys no useQuery declares: {unknown}"


def test_the_query_key_scan_can_see_a_bogus_key():
    assert "boardCurrentMessage" not in _query_key_prefixes_in_use()
    assert "board-current-message" in _query_key_prefixes_in_use()


def test_the_source_scan_actually_found_the_drawer():
    assert "toastForToolResult" in DRAWER_SOURCE
    assert "queryKeysForTool" in DRAWER_SOURCE
    assert len(_api_calls(DRAWER_SOURCE)) >= 5
    assert any(CHOREOGRAPHY_DIR.rglob("*.ts"))


def test_the_forbidden_call_scan_can_see_a_forbidden_call():
    planted = DRAWER_SOURCE + "\n// await api.enablePlugin(id);\n"
    assert _api_calls(planted) & FORBIDDEN_DIRECT_API_CALLS == {"enablePlugin"}
