"""The ops layer is the live path for chat, and the browser cannot take it back.

Phase 2, Task 11. ``src/ops`` was built so the chat and MCP surfaces could
not diverge, but the web drawer never called it: it carried its own
``switch (call.op)`` over a dozen REST endpoints. The layer had zero
production callers on the chat path, and the two surfaces drifted anyway
(three live divergences, pinned in ``tests/test_chat_op_http_parity.py``).

Behavioural parity is asserted over HTTP in that file. What this file adds
is the *structural* guard: a future edit that re-implements a server-side
operation in ``global-ai-chat-drawer.tsx`` has to delete a test to land.

Everything here reads the real TSX, so it fails on a rename rather than
passing vacuously — ``test_the_source_scan_actually_found_the_dispatcher``
proves the parser is looking at something.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.ops import OPERATIONS

REPO_ROOT = Path(__file__).resolve().parent.parent
DRAWER = REPO_ROOT / "web/src/components/global-ai-chat-drawer.tsx"
DRAWER_SOURCE = DRAWER.read_text(encoding="utf-8")

#: REST client methods that existed only to execute a chat op in the browser.
#: Each one was the body of a ``handle<Op>`` callback before Task 11; any of
#: them reappearing in the drawer means an operation grew a second
#: implementation next to its executor.
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
}

#: The schedule mutations the drawer may still call directly, and why. The
#: chat grammar's ``create_schedule`` has no ``start_type`` /
#: ``*_sun_offset`` fields, so restoring a deleted sunrise schedule through
#: the ops endpoint would silently downgrade it to a fixed clock time.
#: Confined to the toast helper — asserted below, not just documented.
UNDO_ONLY_API_CALLS = {"createSchedule", "updateSchedule", "deleteSchedule"}


def _chat_ops(*, client_side: bool) -> set[str]:
    return {op.chat_name for op in OPERATIONS if op.chat_name and op.client_side is client_side}


def _declared_server_ops() -> list[str]:
    """The op names the drawer declares it delegates to the server."""
    match = re.search(r"const SERVER_EXECUTED_OPS = \[(.*?)\] as const;", DRAWER_SOURCE, re.S)
    assert match, "global-ai-chat-drawer.tsx no longer declares SERVER_EXECUTED_OPS"
    return re.findall(r'"([a-z_]+)"', match.group(1))


def _api_calls(source: str) -> set[str]:
    return set(re.findall(r"\bapi\.([A-Za-z0-9_]+)\(", source))


def _toast_helper_source() -> str:
    start = DRAWER_SOURCE.index("const showServerOpToast = useCallback(")
    end = DRAWER_SOURCE.index("const runServerOp = useCallback(")
    return DRAWER_SOURCE[start:end]


# ---------------------------------------------------------------------------
# The drawer's op list and the registry are one list
# ---------------------------------------------------------------------------


def test_drawer_delegates_exactly_the_registrys_server_side_chat_ops():
    """No op may be server-side in the registry but browser-side in the UI."""
    declared = set(_declared_server_ops())
    expected = _chat_ops(client_side=False)
    assert declared == expected, (
        "the drawer's SERVER_EXECUTED_OPS and src/ops/registry.py disagree.\n"
        f"  drawer only:   {sorted(declared - expected)}\n"
        f"  registry only: {sorted(expected - declared)}"
    )


def test_the_drawer_op_list_is_sorted_and_unique():
    declared = _declared_server_ops()
    assert declared == sorted(declared), "keep SERVER_EXECUTED_OPS sorted so diffs stay readable"
    assert len(declared) == len(set(declared))


def test_every_chat_op_is_either_server_executed_or_client_side():
    """The grammar has no third category the UI could quietly invent."""
    server = _chat_ops(client_side=False)
    client = _chat_ops(client_side=True)
    assert server & client == set()
    from src.ops.grammar import _OP_REGISTRY

    assert server | client == set(_OP_REGISTRY)


def test_client_side_ops_are_not_delegated_to_the_server():
    declared = set(_declared_server_ops())
    assert declared & _chat_ops(client_side=True) == set()


# ---------------------------------------------------------------------------
# The browser cannot re-grow an executor
# ---------------------------------------------------------------------------


def test_no_server_executed_op_has_a_browser_side_rest_implementation():
    """The REST calls the per-op handlers used are gone from the drawer."""
    offenders = sorted(_api_calls(DRAWER_SOURCE) & FORBIDDEN_DIRECT_API_CALLS)
    assert offenders == [], (
        "global-ai-chat-drawer.tsx calls REST endpoints that belong to a "
        "server-executed operation. Route the op through "
        "api.executeAiOperation (POST /ai/operations) instead — that is the "
        "seam that keeps the chat and MCP surfaces on one executor. "
        f"Offending calls: {offenders}"
    )


def test_no_handle_callback_survives_for_a_server_executed_op():
    """``const handleEnablePlugin = ...`` is the shape of the old dispatcher."""
    camel = {"".join(part.title() for part in op.split("_")) for op in _declared_server_ops()}
    offenders = sorted(name for name in camel if f"const handle{name}" in DRAWER_SOURCE)
    assert offenders == [], f"server-executed ops must not have their own browser handler: {offenders}"


def test_schedule_mutations_remain_confined_to_the_undo_affordances():
    """The three allowed direct calls exist only inside the toast helper."""
    helper = _toast_helper_source()
    outside = _api_calls(DRAWER_SOURCE.replace(helper, "")) & UNDO_ONLY_API_CALLS
    assert outside == set(), (
        "schedule REST mutations may only appear in showServerOpToast's Undo "
        f"actions; found {sorted(outside)} elsewhere in the drawer"
    )
    assert _api_calls(helper) & UNDO_ONLY_API_CALLS, "the Undo affordances disappeared from the toast helper"


def test_the_ops_endpoint_is_the_drawers_only_execution_seam():
    assert DRAWER_SOURCE.count("api.executeAiOperation(") == 1


# ---------------------------------------------------------------------------
# Guarding the guard
# ---------------------------------------------------------------------------


def test_the_source_scan_actually_found_the_dispatcher():
    """A parser that matches nothing would make every test above vacuous."""
    assert len(_declared_server_ops()) >= 13
    assert "runServerOp" in DRAWER_SOURCE
    assert len(_api_calls(DRAWER_SOURCE)) >= 5
    assert "const showServerOpToast = useCallback(" in DRAWER_SOURCE


def test_the_forbidden_call_scan_can_see_a_forbidden_call():
    """Non-vacuity for the guard above: plant one and watch the scan find it."""
    planted = DRAWER_SOURCE + "\n// await api.enablePlugin(id);\n"
    assert _api_calls(planted) & FORBIDDEN_DIRECT_API_CALLS == {"enablePlugin"}
