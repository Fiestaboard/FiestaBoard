"""The operation registry must cover both grammars, exactly.

Issue #1764 collapsed the chat-op grammar and the MCP tools onto one set of
canonical executors. These tests pin the mapping:

- every chat op name resolves in the registry (client-side ops included);
- every MCP tool the registry claims to back is really registered;
- client-side ops carry no executor and refuse to execute();
- chat-grammar execution validates args with the same schema
  ``parse_tool_call`` uses, then actually reaches the executor (asserted
  by re-reading persisted state, in the spirit of
  tests/test_mcp_state_effects.py).
"""

from __future__ import annotations

import asyncio

import pytest

from src.ai.chat_ops import _OP_REGISTRY as CHAT_OPS
from src.ai.chat_ops import ToolCallValidationError
from src.ops import (
    OPERATIONS,
    ClientSideOperationError,
    execute,
    get_operation,
    operation_names,
)

# ---------------------------------------------------------------------------
# Registry shape
# ---------------------------------------------------------------------------

EXPECTED_CANONICAL = {
    "create_page",
    "update_page",
    "delete_page",
    "set_active_page",
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    "set_schedule_mode",
    "create_collection",
    "update_collection",
    "delete_collection",
    "install_plugin",
    "configure_plugin",
    "enable_plugin",
    "disable_plugin",
    "uninstall_plugin",
    "update_plugin",
    "update_setting",
    "trigger_system_update",
    # client-side chat ops, registered so the registry is the whole grammar
    "apply_patch",
    "suggest_variables",
    "navigate_to_page",
    "navigate_to_schedule",
    "update_task_list",
}


def test_canonical_operation_set_is_pinned():
    assert {op.name for op in OPERATIONS} == EXPECTED_CANONICAL


def test_every_chat_op_resolves_in_the_registry():
    """The registry describes the whole chat grammar, not a subset."""
    chat_names = {op.chat_name for op in OPERATIONS if op.chat_name}
    assert chat_names == set(CHAT_OPS), (
        "chat grammar and ops registry have drifted.\n"
        f"  chat only: {sorted(set(CHAT_OPS) - chat_names)}\n"
        f"  registry only: {sorted(chat_names - set(CHAT_OPS))}"
    )
    for name in CHAT_OPS:
        assert get_operation(name) is not None


def test_client_side_flag_and_executor_are_mutually_exclusive():
    for op in OPERATIONS:
        if op.client_side:
            assert op.executor is None, f"{op.name} is client_side but has an executor"
            assert op.mcp_tool is None, f"{op.name} is client_side but claims an MCP tool"
        else:
            assert op.executor is not None, f"{op.name} has no executor and is not client_side"


def test_every_chat_named_executor_op_has_an_args_adapter():
    for op in OPERATIONS:
        if op.chat_name and not op.client_side:
            assert op.adapt_chat_args is not None, f"{op.name} accepts chat name {op.chat_name} but cannot adapt args"


def test_alias_resolution_covers_both_spellings_of_shared_ops():
    assert get_operation("update_plugin_config") is get_operation("configure_plugin")
    assert get_operation("replace_page") is get_operation("create_page")


def test_unknown_operation_name_raises():
    with pytest.raises(KeyError):
        get_operation("definitely_not_an_op")


def test_operation_names_include_both_grammars():
    names = operation_names()
    assert "update_plugin_config" in names  # chat spelling
    assert "configure_plugin" in names  # MCP spelling


# ---------------------------------------------------------------------------
# MCP coverage — every tool the registry claims must really be registered
# ---------------------------------------------------------------------------


def test_registry_mcp_tools_are_registered_mcp_tools():
    pytest.importorskip("mcp", reason="mcp package not installed")
    from src.mcp_server import _build_mcp_server

    mcp = _build_mcp_server()
    assert mcp is not None
    registered = set(mcp._tool_manager._tools)
    claimed = {op.mcp_tool for op in OPERATIONS if op.mcp_tool}
    phantom = claimed - registered
    assert not phantom, f"ops registry claims MCP tools that do not exist: {sorted(phantom)}"


# ---------------------------------------------------------------------------
# execute() semantics
# ---------------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


def test_execute_refuses_client_side_ops():
    with pytest.raises(ClientSideOperationError):
        _run(execute("apply_patch", {"changes": []}))


def test_execute_validates_chat_args_with_the_chat_schema():
    """A chat-grammar call goes through the same validation parse_tool_call
    applies — bad args fail before any executor runs."""
    with pytest.raises(ToolCallValidationError):
        _run(execute("update_plugin_config", {"config": {}}))  # plugin_id missing


def test_execute_unknown_name_raises_key_error():
    with pytest.raises(KeyError):
        _run(execute("no_such_op", {}))


# ---------------------------------------------------------------------------
# execute() reaches real executors — asserted on re-read state, no mocks
# ---------------------------------------------------------------------------


@pytest.fixture
def services(tmp_path, monkeypatch):
    """Real page/schedule/collection services on throwaway storage."""
    from src.collections.service import CollectionService
    from src.collections.storage import CollectionStorage
    from src.pages.service import PageService
    from src.pages.storage import PageStorage
    from src.schedules.service import ScheduleService
    from src.schedules.storage import ScheduleStorage

    pages = PageService(PageStorage(str(tmp_path / "pages.json")))
    schedules = ScheduleService(ScheduleStorage(str(tmp_path / "schedules.json")))
    collections = CollectionService(CollectionStorage(str(tmp_path / "collections.json")))
    monkeypatch.setattr("src.pages.service._page_service", pages)
    monkeypatch.setattr("src.schedules.service._schedule_service", schedules)
    monkeypatch.setattr("src.collections.service._collection_service", collections)
    return {"pages": pages, "schedules": schedules, "collections": collections}


FLAGSHIP_TEMPLATE = ["HELLO", "", "", "", "", ""]


def test_execute_replace_page_creates_a_persisted_page(services):
    result = _run(
        execute(
            "replace_page",
            {"name": "From Chat Grammar", "template": FLAGSHIP_TEMPLATE, "duration_seconds": 120},
        )
    )
    assert result["status"] == "success"
    stored = services["pages"].get_page(result["page_id"])
    assert stored is not None
    assert stored.name == "From Chat Grammar"
    assert stored.duration_seconds == 120


def test_execute_update_schedule_via_chat_name_changes_only_supplied_fields(services):
    page = _run(execute("create_page", {"name": "P", "template_lines": FLAGSHIP_TEMPLATE}))
    created = _run(
        execute(
            "create_schedule",
            {"page_id": page["page_id"], "start_time": "07:00", "end_time": "09:00", "day_pattern": "weekdays"},
        )
    )
    assert created["status"] == "success"

    updated = _run(execute("update_schedule", {"schedule_id": created["schedule_id"], "start_time": "08:00"}))
    assert updated["status"] == "success"

    stored = next(s for s in services["schedules"].list_schedules() if s.id == created["schedule_id"])
    assert stored.start_time == "08:00"
    assert stored.end_time == "09:00", "a partial update must not wipe end_time (#1764 divergence 3)"
