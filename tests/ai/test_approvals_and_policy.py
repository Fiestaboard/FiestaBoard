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


def test_one_caller_cannot_push_out_another_callers_pauses():
    store = PendingCallStore(max_entries=256, max_per_owner=4)
    store.record("web:admin:admin", "mine", "delete_page", {})
    for n in range(50):
        store.record("mobile:control:admin", f"flood{n}", "delete_page", {})
    assert store.take("web:admin:admin", "mine") is not None
    # The flooding caller keeps only its own newest few.
    assert store.take("mobile:control:admin", "flood0") is None
    assert store.take("mobile:control:admin", "flood49") is not None


def test_recorded_nested_args_are_a_deep_copy():
    store = PendingCallStore()
    args = {"values": {"providers": [{"id": "p"}]}}
    store.record("admin", "c1", "update_setting", args)
    args["values"]["providers"][0]["id"] = "changed"
    assert store.take("admin", "c1").args == {"values": {"providers": [{"id": "p"}]}}


def test_always_pauses_covers_the_system_and_credential_setting_categories():
    from src.ops.registry import always_pauses

    assert always_pauses("restart_system", {})
    assert always_pauses("install_plugin", {"plugin_id": "x"})
    for category, values in [
        ("release_channel", {"channel": "beta"}),
        ("auto_update", {"interval": "daily"}),
        ("hdmi_kiosk", {"enabled": False}),
        ("plugins", {"auto_update": False}),
        ("ai", {"providers": []}),
        ("ai", "not a dict"),
    ]:
        assert always_pauses("update_setting", {"category": category, "values": values}), category
    for category, values in [
        ("plugins", {"transition_plugins_enabled": True}),
        ("ai", {"enabled": True}),
        ("general", {"welcome_message": "x"}),
    ]:
        assert not always_pauses("update_setting", {"category": category, "values": values}), category
    assert not always_pauses("update_page", {"category": "release_channel"})


def test_always_pauses_covers_calls_that_repoint_a_stored_key():
    from src.ops.registry import always_pauses

    assert always_pauses("update_board", {"board_id": "b", "host": "h"})
    assert always_pauses("update_board", {"board_id": "b", "api_mode": "cloud"})
    assert not always_pauses("update_board", {"board_id": "b", "name": "Kitchen"})
    for key in ("broker_host", "broker_port", "host", "port"):
        assert always_pauses("update_setting", {"category": "mqtt", "values": {key: "x"}}), key
    assert not always_pauses("update_setting", {"category": "mqtt", "values": {"enabled": True}})
