"""Unit tests: the pending-call store and the chat tool policy."""

from __future__ import annotations

import asyncio

from src.ai.approvals import PendingCallStore
from src.ai.mcp_bridge import ToolDescriptor, ToolOutcome
from src.ai.tool_policy import ChatToolPolicy, PolicedToolBackend


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_a_recorded_pause_is_taken_once():
    store = PendingCallStore()
    store.record("admin", "c1", "delete_page", {"page_id": "p"})
    first = store.take("admin", "c1")
    assert first is not None and first.name == "delete_page" and first.args == {"page_id": "p"}
    assert store.take("admin", "c1") is None


def test_a_pause_belongs_to_the_caller_it_was_made_for():
    store = PendingCallStore()
    store.record("admin", "c1", "delete_page", {})
    assert store.take("anonymous", "c1") is None
    assert store.take("admin", "c1") is not None


def test_a_pause_expires():
    clock = Clock()
    store = PendingCallStore(ttl_seconds=60, clock=clock)
    store.record("admin", "c1", "delete_page", {})
    clock.now += 61
    assert store.take("admin", "c1") is None


def test_the_store_is_bounded_oldest_first():
    store = PendingCallStore(max_entries=2)
    for call_id in ("a", "b", "c"):
        store.record("admin", call_id, "delete_page", {})
    assert store.take("admin", "a") is None
    assert store.take("admin", "b") is not None and store.take("admin", "c") is not None


def test_recorded_args_are_a_copy():
    store = PendingCallStore()
    args = {"page_id": "p"}
    store.record("admin", "c1", "delete_page", args)
    args["page_id"] = "other"
    assert store.take("admin", "c1").args == {"page_id": "p"}


def _install_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        name="install_plugin",
        title="Install plugin",
        description="Install from the registry or from a public git URL.",
        input_schema={
            "type": "object",
            "properties": {"plugin_id": {}, "auto_enable": {}, "repository": {}, "branch": {}, "initial_config": {}},
        },
        read_only=False,
        destructive=True,
        idempotent=False,
        open_world=True,
        source="mcp",
    )


class Recording:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self):
        return [_install_descriptor()]

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        return ToolOutcome(status="ok", result={})


def test_the_policy_refuses_git_install_args():
    policy = ChatToolPolicy()
    assert policy.refusal("install_plugin", {"repository": "https://example.invalid/x.git"})
    assert policy.refusal("install_plugin", {"plugin_id": "weather", "branch": "dev"})
    assert policy.refusal("install_plugin", {"plugin_id": "weather"}) is None
    assert policy.refusal("install_plugin", {"plugin_id": "weather", "repository": None, "branch": ""}) is None


def test_the_policed_backend_blocks_before_the_inner_call():
    inner = Recording()
    backend = PolicedToolBackend(inner)
    outcome = asyncio.run(backend.call_tool("install_plugin", {"repository": "file:///tmp/x"}))
    assert outcome.status == "blocked" and "Add from Git" in outcome.error
    assert inner.calls == []
    assert asyncio.run(backend.call_tool("install_plugin", {"plugin_id": "weather"})).status == "ok"
    assert inner.calls == [("install_plugin", {"plugin_id": "weather"})]


def test_the_policed_backend_does_not_teach_git_args():
    taught = asyncio.run(PolicedToolBackend(Recording()).list_tools())[0]
    assert set(taught.input_schema["properties"]) == {"plugin_id", "auto_enable", "initial_config"}
    assert "git url" not in taught.description.lower() or "not available" in taught.description.lower()
