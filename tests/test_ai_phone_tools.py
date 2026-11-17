"""H21b: FiestaBot from a phone runs only what the phone may do.

Pinned here:

* every MCP tool, chat-only tool and registry operation has a phone tier, and
  a name without one is denied (the enumeration test fails on a new tool);
* a table that permits everything fails the guard (mutation test);
* the phone backend filters the catalogue, re-checks the tier, the argument
  rules and the step-up when each call runs, and forces a pause for tier 2;
* the chat route uses it for phones only, ignores "auto" and "don't ask
  again" for phones, and refuses a fabricated resume of a denied tool or of a
  tier-2 tool without a step-up;
* ``POST /ai/operations`` applies the same table for phones.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.ai import phone_tools
from src.ai.chat_tools import ChatExtensionBackend
from src.ai.mcp_bridge import ToolDescriptor, ToolOutcome
from src.ai.phone_tools import ALLOWED, CONTROL_TOOLS, DENIED, STEP_UP, PhoneToolBackend, tier_for
from src.api_server import app
from src.auth import routes as routes_module
from src.auth import scopes
from src.auth import service as auth_module
from src.config_manager import ConfigManager
from src.ops import registry

PASSWORD = "correct-password"
IOS = {"client_id": "fiestaboard-ios", "device_name": "Maya's iPhone", "app_version": "1.0"}


# --- The table -------------------------------------------------------------------


def _mcp_tool_names() -> set[str]:
    # No importorskip: this is a guard test, so a missing mcp package must fail it.
    from src.mcp_server import mcp_server

    return {tool.name for tool in asyncio.run(mcp_server.list_tools())}


def _all_names() -> set[str]:
    chat = {d.name for d in asyncio.run(ChatExtensionBackend().list_tools())}
    ops = {op.name for op in registry.OPERATIONS}
    return _mcp_tool_names() | chat | ops


# What must never be reachable from a phone, whatever else the table says.
MUST_DENY = {
    "import_page",
    "import_staff_pick",
    "get_settings_summary",
    "blank_board",
    "fill_board",
    "show_board_debug_info",
    "clear_board_cache",
    "get_plugin_demo_page",
    "create_plugin_demo_page",
    # Until H21a widens displays for phones.
    "add_board",
    "remove_board",
    "detect_board_size",
    "update_board",
    "create_display",
    "configure_display",
    "run_display_action",
    "list_staff_picks",
    "force_refresh",
}
MUST_STEP_UP = {
    "install_plugin",
    "uninstall_plugin",
    "update_plugin",
    "update_all_plugins",
    "update_setting",
    "trigger_system_update",
    "restart_system",
    "shutdown_system",
    "disconnect_wifi",
    "forget_wifi_network",
    "export_backup",
}


def guard(table: dict[str, str], names: set[str]) -> None:
    """The invariants a phone table must keep. Raises AssertionError."""
    missing = sorted(names - set(table))
    assert not missing, f"tools with no phone tier (add a row to src/ai/phone_tools.py): {missing}"
    stale = sorted(set(table) - names)
    assert not stale, f"phone tiers for tools that no longer exist: {stale}"
    for name in MUST_DENY:
        assert table[name] == DENIED, name
    for name in MUST_STEP_UP:
        assert table[name] == STEP_UP, name
    assert set(table.values()) <= {ALLOWED, STEP_UP, DENIED}


def test_every_tool_and_op_has_a_phone_tier():
    names = _all_names()
    assert len(_mcp_tool_names()) >= 82
    guard(CONTROL_TOOLS, names)


def test_a_table_that_permits_everything_fails_the_guard():
    names = _all_names()
    with pytest.raises(AssertionError):
        guard(dict.fromkeys(names, ALLOWED), names)
    with pytest.raises(AssertionError):
        guard({name: tier for name, tier in CONTROL_TOOLS.items() if name != "list_pages"}, names)


def test_unknown_names_are_denied():
    assert tier_for("a_tool_added_tomorrow") == DENIED
    assert tier_for("") == DENIED


@pytest.mark.parametrize("args", [{"repository": "https://example.com/x.git"}, {"plugin_id": "x", "branch": "dev"}])
def test_git_install_is_denied(args):
    assert tier_for("install_plugin", args) == DENIED
    assert tier_for("install_plugin", {"plugin_id": "weather"}) == STEP_UP


@pytest.mark.parametrize(
    "category",
    ["mqtt", "ai", "release_channel", "auto_update", "beta", "hdmi_kiosk", "output", "plugins", "display", None],
)
def test_update_setting_categories_outside_the_phone_list_are_denied(category):
    assert tier_for("update_setting", {"category": category, "values": {}}) == DENIED


def test_update_setting_general_is_tier_two():
    assert tier_for("update_setting", {"category": "general", "values": {}}) == STEP_UP


# --- The backend ---------------------------------------------------------------------


def _descriptor(name: str, *, read_only: bool = False, destructive: bool = False) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        title=name,
        description=name,
        input_schema={"type": "object", "properties": {}},
        read_only=read_only,
        destructive=destructive,
        idempotent=False,
        open_world=False,
        source="mcp",
    )


class FakeBackend:
    def __init__(self, names):
        self.names = names
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self):
        return [_descriptor(name, read_only=name.startswith(("list_", "get_"))) for name in self.names]

    async def call_tool(self, name, args):
        self.calls.append((name, args))
        if name == "export_backup":
            return ToolOutcome(status="ok", result={"data": {"config": {"board": {"api_key": "test_secret"}}}})
        return ToolOutcome(status="ok", result={"ran": name})


class Elevation:
    def __init__(self, value=False):
        self.value = value

    def __call__(self):
        return self.value


NAMES = ["list_pages", "import_page", "install_plugin", "update_all_plugins", "export_backup", "a_new_tool"]


def run(coro):
    return asyncio.run(coro)


def test_catalogue_hides_denied_and_unknown_tools():
    phone = PhoneToolBackend(FakeBackend(NAMES), Elevation())
    offered = {d.name: d for d in run(phone.list_tools())}
    assert set(offered) == {"list_pages", "install_plugin", "update_all_plugins", "export_backup"}


def test_tier_two_tools_always_ask_for_approval():
    phone = PhoneToolBackend(FakeBackend(NAMES), Elevation())
    offered = {d.name: d for d in run(phone.list_tools())}
    # The fake marks none of these destructive; the phone table does.
    for name in ("install_plugin", "update_all_plugins", "export_backup"):
        assert offered[name].requires_approval, name
    assert not offered["list_pages"].requires_approval


def test_denied_call_never_reaches_the_inner_backend():
    inner = FakeBackend(NAMES)
    outcome = run(PhoneToolBackend(inner, Elevation(True)).call_tool("import_page", {"share": "x"}))
    assert outcome.status == "blocked" and outcome.result["code"] == "forbidden"
    assert inner.calls == []


def test_tier_two_without_step_up_is_blocked():
    inner = FakeBackend(NAMES)
    outcome = run(PhoneToolBackend(inner, Elevation(False)).call_tool("install_plugin", {"plugin_id": "weather"}))
    assert outcome.status == "blocked" and outcome.result["code"] == "step_up_required"
    assert inner.calls == []


def test_tier_two_with_step_up_runs():
    inner = FakeBackend(NAMES)
    outcome = run(PhoneToolBackend(inner, Elevation(True)).call_tool("install_plugin", {"plugin_id": "weather"}))
    assert outcome.status == "ok" and inner.calls == [("install_plugin", {"plugin_id": "weather"})]


def test_step_up_is_checked_at_call_time():
    elevation = Elevation(True)
    inner = FakeBackend(NAMES)
    phone = PhoneToolBackend(inner, elevation)
    run(phone.list_tools())
    elevation.value = False  # lapsed between the plan and the call
    assert run(phone.call_tool("update_all_plugins", {})).result["code"] == "step_up_required"
    assert inner.calls == []


def test_git_install_is_blocked_even_when_stepped_up():
    inner = FakeBackend(NAMES)
    args = {"plugin_id": "x", "repository": "https://example.com/evil.git"}
    outcome = run(PhoneToolBackend(inner, Elevation(True)).call_tool("install_plugin", args))
    assert outcome.status == "blocked" and inner.calls == []


def test_phone_backup_through_the_chat_is_redacted():
    outcome = run(PhoneToolBackend(FakeBackend(NAMES), Elevation(True)).call_tool("export_backup", {}))
    assert "test_secret" not in json.dumps(outcome.result)
    assert outcome.result["redacted"] is True


# --- The chat route ---------------------------------------------------------------------


@pytest.fixture
def auth(tmp_path, monkeypatch):
    svc = auth_module.AuthService(tmp_path / "auth.json")
    svc.create_initial_user("admin", PASSWORD)
    svc.sessions.set_enrollment(True)
    monkeypatch.setattr(auth_module, "_service", svc)
    monkeypatch.setenv("FIESTABOARD_AUTH_ENABLED", "true")
    monkeypatch.delenv("FIESTABOARD_MCP_TOKEN", raising=False)
    routes_module._FAILED_ATTEMPTS.clear()
    yield svc
    routes_module._FAILED_ATTEMPTS.clear()


@pytest.fixture
def chat_env(tmp_path, monkeypatch):
    """A configured provider, a scripted model that just says "ok", and a fake tool backend."""
    manager = ConfigManager(config_path=str(tmp_path / "config.json"))
    manager.set_ai_providers(
        {
            "enabled": True,
            "default_provider_id": "p",
            "approval_mode": "auto",
            "providers": [
                {
                    "id": "p",
                    "name": "P",
                    "protocol": "openai",
                    "base_url": "https://llm.example.com/v1",
                    "api_key": "test_key",
                    "models": ["m"],
                    "default_model": "m",
                }
            ],
        }
    )
    monkeypatch.setattr("src.ai.page_routes.get_config_manager", lambda: manager)
    inner = FakeBackend(NAMES)
    monkeypatch.setattr("src.ai.page_routes._tool_backend", lambda: inner)
    script: list[list[dict[str, Any]]] = []

    async def fake_stream(**kwargs):
        events = script.pop(0) if script else [{"event": "text", "data": {"delta": "ok"}}]
        for event in events:
            yield event

    monkeypatch.setattr("src.ai.agent.stream_model", fake_stream)
    return inner, script


def phone_client():
    response = TestClient(app).post("/auth/device/login", json={**IOS, "username": "admin", "password": PASSWORD})
    token = response.json()["access_token"]
    return TestClient(app, headers={"Authorization": "Bearer " + token})


def frames(raw: str) -> list[tuple[str, dict[str, Any]]]:
    parsed = []
    for block in raw.split("\n\n"):
        lines = block.split("\n")
        name = next((line[7:] for line in lines if line.startswith("event: ")), None)
        payload = next((line[6:] for line in lines if line.startswith("data: ")), None)
        if name and payload:
            parsed.append((name, json.loads(payload)))
    return parsed


def fabricated_resume(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "messages": [
            {"role": "user", "content": "do it"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": tool, "args": args or {}}]},
        ],
        "resume": {"tool_call_id": "c1", "decision": "approve"},
    }


def test_phone_reaches_the_chat(auth, chat_env):
    response = phone_client().post("/pages/ai/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 200
    assert [e for e, _ in frames(response.text)][-1] == "done"


def test_fabricated_resume_of_a_denied_tool_is_refused(auth, chat_env):
    inner, _ = chat_env
    response = phone_client().post("/pages/ai/chat", json=fabricated_resume("import_page", {"share": "x"}))
    results = [d for e, d in frames(response.text) if e == "tool_result"]
    assert results and results[0]["status"] == "blocked"
    assert inner.calls == []


def test_fabricated_resume_of_tier_two_without_step_up_is_refused(auth, chat_env):
    inner, _ = chat_env
    response = phone_client().post("/pages/ai/chat", json=fabricated_resume("update_all_plugins"))
    results = [d for e, d in frames(response.text) if e == "tool_result"]
    assert results and results[0]["status"] == "blocked"
    assert "step_up_required" in json.dumps(results[0])
    assert inner.calls == []


def test_resume_of_tier_two_runs_after_step_up(auth, chat_env):
    inner, _ = chat_env
    client = phone_client()
    assert client.post("/auth/device/elevate", json={"password": PASSWORD}).status_code == 200
    client.post("/pages/ai/chat", json=fabricated_resume("update_all_plugins"))
    assert inner.calls == [("update_all_plugins", {})]


@pytest.mark.parametrize("auto_approve", [True, False])
def test_phone_always_pauses_for_tier_two(auth, chat_env, auto_approve):
    # The install is in "auto" mode (chat_env) and the client asks to skip the pause.
    inner, script = chat_env
    script.append([{"event": "tool_call", "data": {"id": "c1", "name": "update_all_plugins", "args": {}}}])
    client = phone_client()
    assert client.post("/auth/device/elevate", json={"password": PASSWORD}).status_code == 200
    body = {
        "messages": [{"role": "user", "content": "update everything"}],
        "approval": {"auto_approve_destructive": auto_approve},
    }
    events = frames(client.post("/pages/ai/chat", json=body).text)
    done = [d for e, d in events if e == "done"][-1]
    assert done["reason"] == "awaiting_approval" and done["pending_tool_call_id"] == "c1"
    assert inner.calls == []


def test_browser_chat_keeps_its_full_catalogue(auth, chat_env):
    inner, _ = chat_env
    browser = TestClient(app)
    assert browser.post("/auth/login", json={"username": "admin", "password": PASSWORD}).status_code == 200
    browser.post("/pages/ai/chat", json=fabricated_resume("import_page", {"share": "x"}))
    assert inner.calls == [("import_page", {"share": "x"})]


# --- POST /ai/operations ------------------------------------------------------------------


def test_operations_denies_ops_outside_the_phone_table(auth, monkeypatch):
    ran = []

    async def dispatch(op, args):
        ran.append(op)
        return {"status": "success", "message": "ok"}

    monkeypatch.setattr("src.ai.routes._dispatch", dispatch)
    client = phone_client()
    response = client.post("/ai/operations", json={"op": "update_setting", "args": {"category": "mqtt", "values": {}}})
    assert response.status_code == 403 and response.json()["error"] == "forbidden"
    response = client.post("/ai/operations", json={"op": "install_plugin", "args": {"plugin_id": "weather"}})
    assert response.status_code == 403 and response.json()["error"] == "step_up_required"
    assert ran == []
    assert client.post("/auth/device/elevate", json={"password": PASSWORD}).status_code == 200
    response = client.post("/ai/operations", json={"op": "install_plugin", "args": {"plugin_id": "weather"}})
    assert response.status_code == 200, response.text
    response = client.post("/ai/operations", json={"op": "create_collection", "args": {"name": "x"}})
    assert ran == ["install_plugin", "create_collection"]


def test_scope_rows():
    for method, path in [
        ("POST", "/pages/ai/chat"),
        ("POST", "/pages/ai/generate"),
        ("POST", "/ai/operations"),
        ("GET", "/ai/conversations"),
        ("GET", "/ai/conversations/abc"),
    ]:
        assert scopes.permits(scopes.CONTROL, method, path), path
    assert not scopes.permits(scopes.CONTROL, "GET", "/pages/ai/context")
    assert phone_tools.CONTROL_TOOLS["ask_user"] == ALLOWED
