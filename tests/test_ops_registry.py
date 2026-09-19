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
    # MCP-only plugin ops covering the Integrations page (instances, demo
    # pages, bulk updates); the chat grammar has no spelling for them.
    "create_plugin_instance",
    "delete_plugin_instance",
    "create_plugin_demo_page",
    "check_plugin_updates",
    "update_all_plugins",
    "update_setting",
    "trigger_system_update",
    # MCP-only server op since #1765 — the REST POST /send-message
    # equivalent; the chat grammar has no spelling for it today.
    "send_message",
    # MCP-only server ops for the page editor's sibling features: share
    # strings, staff picks and the Transition Lab. Like send_message, the
    # chat grammar has no spelling for them — the chat reaches them as
    # MCP tools through the in-process server.
    "import_page",
    "import_staff_pick",
    "test_transition_live",
    "restore_board",
    # MCP-only server ops for the Schedules page's default page and the Home
    # page's board-state controls; the chat grammar has no spellings.
    "set_default_page",
    "pause_board",
    "resume_board",
    "set_temporary_override",
    "cancel_temporary_override",
    "force_refresh",
    # MCP-only server ops covering the Settings page (boards, panels,
    # network, system, debug). The in-app chat reaches them through the MCP
    # catalog, not the legacy chat grammar.
    "restart_system",
    "shutdown_system",
    "update_board",
    "add_board",
    "remove_board",
    "identify_tile",
    "create_panel",
    "update_panel",
    "delete_panel",
    "disconnect_wifi",
    "forget_wifi_network",
    "blank_board",
    "fill_board",
    "show_board_debug_info",
    "clear_board_cache",
    # client-side chat ops, registered so the registry is the whole grammar.
    # ``replace_page`` joined them in Phase 2 Task 11: it edits the page
    # mounted in the editor (like ``apply_patch``), which is what the system
    # prompt teaches and what the browser has always done. #1764's alias onto
    # ``create_page`` was never exercised — nothing on the chat path called
    # the registry — and executing it server-side would create a second page
    # while leaving the open editor untouched.
    "replace_page",
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


def test_replace_page_is_an_editor_op_not_an_alias_of_create_page():
    """Phase 2 Task 11: the two are different operations, not two spellings.

    ``create_page`` (MCP) persists a new page. ``replace_page`` (chat)
    rewrites the page open in the editor and has no server executor —
    resolving them to the same object would put "create a duplicate page"
    behind a prompt that promises "rewrite what I am looking at".
    """
    assert get_operation("replace_page") is not get_operation("create_page")
    assert get_operation("replace_page").client_side is True
    assert get_operation("create_page").client_side is False
    assert get_operation("create_page").chat_name is None


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


def test_update_setting_has_both_spellings():
    """``update_setting`` is an MCP tool as well as a chat op, so the in-app
    chat can change settings through the same server external clients use."""
    op = get_operation("update_setting")
    assert op.chat_name == "update_setting"
    assert op.mcp_tool == "update_setting"


def test_trigger_system_update_is_an_mcp_tool_not_a_chat_extension():
    """The update used to be a chat-only extension tool; it is a real MCP
    tool now, so external clients and the chat share one implementation."""
    op = get_operation("trigger_system_update")
    assert op.mcp_tool == "trigger_system_update"


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
        _run(execute("update_plugin_config", {"config": {}}, grammar="chat"))  # plugin_id missing


def test_execute_validates_a_shared_spelling_with_the_chat_schema_when_the_caller_used_chat():
    """#1849 item 2, the other direction: ``update_schedule`` is spelled the
    same in both grammars, and a caller who says it used the chat grammar
    gets the chat schema — not a canonical passthrough."""
    with pytest.raises(ToolCallValidationError):
        _run(execute("update_schedule", {"start_time": "08:00"}, grammar="chat"))  # schedule_id missing


def test_execute_refuses_a_chat_only_spelling_under_the_canonical_grammar():
    """The default grammar is canonical, and ``update_plugin_config`` is not a
    canonical name — the call must fail on the name, not fall back to a
    name-equality guess about which schema to apply."""
    with pytest.raises(KeyError):
        _run(execute("update_plugin_config", {"plugin_id": "x", "config": {}}))


def test_execute_refuses_a_canonical_only_spelling_under_the_chat_grammar():
    with pytest.raises(KeyError):
        _run(execute("create_page", {"name": "P", "template_lines": ["HELLO"]}, grammar="chat"))


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


def test_execute_replace_page_refuses_and_persists_nothing(services):
    """Phase 2 Task 11: ``replace_page`` is applied in the editor, not here.

    Was ``test_execute_replace_page_creates_a_persisted_page``, which
    asserted the #1764 alias onto ``create_page``. That alias contradicted
    both the system prompt and the shipped browser behavior; executing it
    server-side would silently create a duplicate page.
    """
    with pytest.raises(ClientSideOperationError):
        _run(execute("replace_page", {"name": "From Chat Grammar", "template": FLAGSHIP_TEMPLATE}))
    assert services["pages"].list_pages() == []


def test_execute_create_page_still_persists_a_page(services):
    """The MCP spelling keeps its executor."""
    result = _run(execute("create_page", {"name": "From MCP", "template_lines": FLAGSHIP_TEMPLATE}))
    assert result["status"] == "success"
    stored = services["pages"].get_page(result["page_id"])
    assert stored is not None
    assert stored.name == "From MCP"


def test_execute_update_schedule_via_chat_name_changes_only_supplied_fields(services):
    page = _run(execute("create_page", {"name": "P", "template_lines": FLAGSHIP_TEMPLATE}))
    created = _run(
        execute(
            "create_schedule",
            {"page_id": page["page_id"], "start_time": "07:00", "end_time": "09:00", "day_pattern": "weekdays"},
            grammar="chat",
        )
    )
    assert created["status"] == "success"

    updated = _run(
        execute("update_schedule", {"schedule_id": created["schedule_id"], "start_time": "08:00"}, grammar="chat")
    )
    assert updated["status"] == "success"

    stored = next(s for s in services["schedules"].list_schedules() if s.id == created["schedule_id"])
    assert stored.start_time == "08:00"
    assert stored.end_time == "09:00", "a partial update must not wipe end_time (#1764 divergence 3)"


def test_execute_by_canonical_name_passes_a_canonical_only_kwarg_to_the_executor(services):
    """#1849 item 2: validation must key on the grammar the caller used.

    ``create_schedule`` is spelled identically in the chat grammar and the
    canonical/MCP one. ``execute()`` used to decide "this is a chat call"
    from that name equality alone, so a canonical caller's ``board_id`` — a
    kwarg the executor takes and the chat schema does not know — was run
    through the chat schema and silently dropped: the schedule landed on
    the default board and the call reported success.
    """
    from src.settings.service import get_settings_service

    stored_boards = get_settings_service().set_boards(
        [{"device_type": "flagship", "name": "Kitchen"}, {"device_type": "note", "name": "Hallway"}]
    )
    note_id = stored_boards.boards[1]["id"]
    # A note-sized page: the executor refuses a page that does not fit the
    # target board, which is itself proof the board_id arrived.
    page = _run(execute("create_page", {"name": "P", "template_lines": ["HELLO", "", ""], "device_type": "note"}))

    created = _run(execute("create_schedule", {"page_id": page["page_id"], "start_time": "07:00", "board_id": note_id}))
    assert created["status"] == "success", created

    # get_schedule, not list_schedules: the latter lists the default board only.
    stored = services["schedules"].get_schedule(created["schedule_id"])
    assert stored is not None, "the schedule the executor reported was not persisted"
    assert stored.board_id == note_id, (
        f"board_id was dropped on the way to the executor (stored {stored.board_id!r}): "
        "the canonical spelling was validated against the chat schema"
    )
