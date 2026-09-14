"""Contract test: every MCP tool declares standard ``ToolAnnotations``.

MCP tool annotations (``readOnlyHint``, ``destructiveHint``,
``idempotentHint``, ``openWorldHint``) are the protocol's own way for a
server to tell a client what a tool does to the world. Clients use them for
two things that matter here:

- **External clients** (Claude Desktop, Claude Code) decide whether to ask
  the user before running a tool. A missing annotation is read as "may be
  destructive", so every delete prompts — and so does every read.
- **The in-app chat** (from the agent-loop work that follows this) treats
  ``readOnlyHint`` tools as free to call mid-turn and pauses only on
  ``destructiveHint`` tools. It never keeps its own list; the server is the
  source of truth, so chat and MCP cannot disagree about which tools need
  approval.

The sets below are pinned on purpose. Adding a tool without deciding its
annotations fails ``test_every_tool_declares_annotations``; changing a
tool's blast radius without updating the pin fails the set tests. Both are
one-line fixes once the decision is made — the point is that it *is* made.

Reading annotations goes through ``model_dump(by_alias=True)`` and the wire
names (``readOnlyHint``), never attribute access: the SDK renamed the Python
attributes between 2.1 (``readOnlyHint``) and 2.2 (``read_only_hint``), and
the aliases are the stable contract.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

pytest.importorskip("mcp", reason="mcp package not installed")

from src.mcp_server import _build_mcp_server

#: Tools that only observe. They run immediately in the chat loop and no
#: client should confirm them.
READ_ONLY = {
    "list_installed_plugins",
    "list_registry_plugins",
    "get_template_variables",
    "get_plugin_data",
    "list_pages",
    "get_page",
    "render_page_preview",
    "preview_saved_page",
    "validate_template",
    "list_schedules",
    "list_collections",
    "get_system_status",
    "get_settings_summary",
    "get_active_page",
    "get_board_content",
}

#: Tools whose effect cannot be undone by calling another tool. These are
#: the only ones the in-app chat pauses on. ``update_*`` tools overwrite, but
#: they are the everyday editing path and the previous state is one
#: ``get_*`` away, so they are deliberately NOT here.
APPROVAL_GATED = {
    "delete_page",
    "delete_schedule",
    "delete_collection",
    "uninstall_plugin",
}

#: Tools that touch something outside this install (the plugin registry
#: over the network, a git remote, a plugin's upstream API).
OPEN_WORLD = {
    "list_registry_plugins",
    "get_plugin_data",
    "install_plugin",
    "update_plugin",
}

#: Calling these twice with the same arguments leaves the same state as
#: calling them once.
IDEMPOTENT = READ_ONLY | {
    "enable_plugin",
    "disable_plugin",
    "configure_plugin",
    "update_plugin",
    "set_active_page",
    "set_schedule_mode",
    "update_setting",
    "update_page",
    "update_schedule",
    "update_collection",
}


@pytest.fixture(scope="module")
def mcp():
    instance = _build_mcp_server()
    assert instance is not None, "mcp installed but _build_mcp_server() returned None"
    return instance


@pytest.fixture(scope="module")
def annotations(mcp) -> dict[str, dict[str, Any] | None]:
    """``{tool_name: annotations-as-wire-dict | None}`` for every tool."""
    out: dict[str, dict[str, Any] | None] = {}
    for name, tool in mcp._tool_manager._tools.items():
        ann = getattr(tool, "annotations", None)
        out[name] = ann.model_dump(by_alias=True, exclude_none=True) if ann is not None else None
    return out


def _names_where(annotations: dict[str, dict[str, Any] | None], key: str, value: bool) -> set[str]:
    return {name for name, ann in annotations.items() if ann is not None and ann.get(key) is value}


def test_every_tool_declares_annotations(annotations):
    missing = sorted(name for name, ann in annotations.items() if ann is None)
    assert not missing, f"tools registered without ToolAnnotations: {missing}"


def test_every_tool_sets_all_four_hints_explicitly(annotations):
    """No hint is left to the client's default. The spec default for a
    missing ``destructiveHint`` is *true*, so an omitted hint is not neutral."""
    hints = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
    incomplete = {
        name: sorted(set(hints) - set(ann))
        for name, ann in annotations.items()
        if ann is not None and set(hints) - set(ann)
    }
    assert not incomplete, f"tools with unset hints: {incomplete}"


def test_read_only_tools_are_exactly_the_pinned_set(annotations):
    assert _names_where(annotations, "readOnlyHint", True) == READ_ONLY


def test_approval_gated_destructive_tools_are_exactly_the_pinned_set(annotations):
    assert _names_where(annotations, "destructiveHint", True) == APPROVAL_GATED


def test_update_tools_are_not_approval_gated(annotations):
    for name in ("update_page", "update_schedule", "update_collection", "update_plugin", "update_setting"):
        assert annotations[name]["destructiveHint"] is False, f"{name} must not pause the chat for approval"


def test_no_read_only_tool_is_marked_destructive(annotations):
    contradictions = sorted(
        _names_where(annotations, "readOnlyHint", True) & _names_where(annotations, "destructiveHint", True)
    )
    assert not contradictions, f"read-only AND destructive: {contradictions}"


def test_open_world_tools_are_exactly_the_pinned_set(annotations):
    assert _names_where(annotations, "openWorldHint", True) == OPEN_WORLD


def test_idempotent_tools_are_exactly_the_pinned_set(annotations):
    assert _names_where(annotations, "idempotentHint", True) == IDEMPOTENT


def test_every_tool_has_a_human_title(annotations):
    untitled = sorted(name for name, ann in annotations.items() if ann is not None and not ann.get("title"))
    assert not untitled, f"tools without a title: {untitled}"


def test_annotations_are_visible_through_list_tools_by_alias(mcp, annotations):
    """What an MCP client actually receives — ``tools/list`` — carries the
    same hints under the wire names, for every tool."""
    listed = asyncio.run(mcp.list_tools())
    by_name = {t.name: t for t in listed}
    assert set(by_name) == set(annotations)
    for name, expected in annotations.items():
        got = by_name[name].annotations
        assert got is not None, f"{name} lost its annotations on the wire"
        assert got.model_dump(by_alias=True, exclude_none=True) == expected
