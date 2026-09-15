"""Chat-only extension tools: the same descriptor shape, explicitly not MCP."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from src.ai.chat_tools import ASK_USER, ChatExtensionBackend


def _run(coro):
    return asyncio.run(coro)


def test_extension_catalog_is_exactly_ask_user_and_trigger_system_update():
    names = {d.name for d in _run(ChatExtensionBackend().list_tools())}
    assert names == {ASK_USER, "trigger_system_update"}


def test_ask_user_is_read_only_and_client_answered():
    d = next(d for d in _run(ChatExtensionBackend().list_tools()) if d.name == ASK_USER)
    assert d.source == "chat" and d.read_only is True and d.requires_approval is False
    assert set(d.input_schema["required"]) == {"question"}
    out = _run(ChatExtensionBackend().call_tool(ASK_USER, {"question": "?"}))
    assert out.status == "error"  # never executed server-side


def test_trigger_system_update_is_destructive_and_uses_the_ops_executor():
    d = next(d for d in _run(ChatExtensionBackend().list_tools()) if d.name == "trigger_system_update")
    assert d.requires_approval is True and d.source == "chat"

    async def fake_executor():
        return {"status": "success", "message": "Update started."}

    with patch("src.ops.executors.trigger_system_update", fake_executor):
        out = _run(ChatExtensionBackend().call_tool("trigger_system_update", {}))
    assert out.status == "ok"
    assert out.result["message"] == "Update started."


def test_trigger_system_update_error_envelope_becomes_error_outcome():
    async def fake_executor():
        return {"status": "error", "error": "No updater sidecar."}

    with patch("src.ops.executors.trigger_system_update", fake_executor):
        out = _run(ChatExtensionBackend().call_tool("trigger_system_update", {}))
    assert out.status == "error" and out.error == "No updater sidecar."
