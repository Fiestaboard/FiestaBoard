"""Chat-only extension tools: the same descriptor shape, explicitly not MCP."""

from __future__ import annotations

import asyncio

import pytest

from src.ai.chat_tools import ASK_USER, ChatExtensionBackend


def _run(coro):
    return asyncio.run(coro)


def test_extension_catalog_is_exactly_ask_user():
    """``trigger_system_update`` left this backend for the MCP server; the
    only tool that is meaningless to an external MCP client is ask_user."""
    names = {d.name for d in _run(ChatExtensionBackend().list_tools())}
    assert names == {ASK_USER}


def test_ask_user_is_read_only_and_client_answered():
    d = next(d for d in _run(ChatExtensionBackend().list_tools()) if d.name == ASK_USER)
    assert d.source == "chat" and d.read_only is True and d.requires_approval is False
    assert set(d.input_schema["required"]) == {"question"}
    out = _run(ChatExtensionBackend().call_tool(ASK_USER, {"question": "?"}))
    assert out.status == "error"  # never executed server-side


def test_trigger_system_update_is_no_longer_served_by_the_chat_backend():
    out = _run(ChatExtensionBackend().call_tool("trigger_system_update", {}))
    assert out.status == "error" and "Unknown tool" in (out.error or "")


def test_trigger_system_update_is_a_destructive_mcp_tool():
    """Where it went: the MCP server, with the approval-gating annotation."""
    pytest.importorskip("mcp", reason="mcp package not installed")
    from src.mcp_server import _build_mcp_server

    mcp = _build_mcp_server()
    tool = mcp._tool_manager._tools["trigger_system_update"]
    hints = tool.annotations.model_dump(by_alias=True, exclude_none=True)
    assert hints["destructiveHint"] is True and hints["readOnlyHint"] is False
