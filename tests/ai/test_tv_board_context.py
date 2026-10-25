"""TV chat must author for its real board and report partial writes honestly."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.ai.prompt_builder import build_prompt
from src.ops.executors import set_active_page


def test_chat_uses_selected_panel_geometry_and_explicit_target():
    board = {"id": "tv-board", "name": "Living room", "device_type": "panel", "grid_rows": 18, "grid_cols": 45}
    ctx = build_prompt("Make weather", "flagship", mode="chat", target_board=board)
    assert (ctx.rows, ctx.cols, ctx.device_type) == (18, 45, "panel")
    assert 'device_type "panel"' in ctx.system_prompt
    assert 'device_type "flagship"' not in ctx.system_prompt
    assert "45 columns x 18 rows" in ctx.system_prompt
    assert '"board_id": "tv-board"' in ctx.system_prompt
    assert '"grid_rows": 18' in ctx.system_prompt
    assert "Do not disable schedules" in ctx.system_prompt


def test_chat_uses_note_array_geometry():
    ctx = build_prompt(
        "Make time",
        "flagship",
        mode="chat",
        target_board={
            "id": "array",
            "device_type": "note_array",
            "notes_wide": 2,
            "notes_tall": 3,
        },
    )
    assert (ctx.rows, ctx.cols, ctx.device_type) == (9, 30, "note_array")
    assert '"notes_wide": 2' in ctx.system_prompt


def test_tv_interaction_prefers_short_choices_with_keyboard_fallback():
    ctx = build_prompt("Make time", "flagship", mode="chat", interaction_mode="tv")
    assert "2–4 short" in ctx.system_prompt
    assert "allow_free_text=true" in ctx.system_prompt
    assert "Avoid unnecessary questions" in ctx.system_prompt
    assert "get_page" in ctx.system_prompt
    assert "before editing" in ctx.system_prompt
    ordinary = build_prompt("Make time", "flagship", mode="chat")
    assert "TV INTERACTION" not in ordinary.system_prompt


def test_active_page_partial_failure_is_not_reported_as_success():
    response = {
        "page_id": "page",
        "board_id": "tv",
        "sent_to_board": False,
        "paused": False,
        "error": "Weather unavailable",
        "warnings": [],
    }
    with patch("src.settings.routes.set_active_page", new=AsyncMock(return_value=response)):
        result = asyncio.run(set_active_page("page", board_id="tv"))
    assert result["status"] == "error"
    assert "Weather unavailable" in result["error"]
    assert "selection was saved" in result["error"]


def test_route_resolves_only_prompt_safe_board_metadata():
    from src.ai.page_routes import _chat_board_context

    with patch(
        "src.board_guards._find_board",
        return_value={
            "id": "tv",
            "name": "Room",
            "device_type": "panel",
            "grid_rows": 18,
            "grid_cols": 45,
            "api_key": "do-not-expose",
            "host": "private-host",
        },
    ):
        board = _chat_board_context("tv")
    assert board["id"] == "tv"
    assert board["grid_cols"] == 45
    assert "api_key" not in board
    assert "host" not in board


def test_unknown_target_is_rejected_instead_of_falling_back_to_primary():
    from fastapi import HTTPException

    from src.ai.page_routes import _chat_board_context

    with patch("src.board_guards._find_board", return_value=None), pytest.raises(HTTPException) as exc:
        _chat_board_context("deleted-tv")
    assert exc.value.status_code == 404


def test_tv_catalog_excludes_admin_and_binds_board_actions():
    from src.ai.tool_catalog import ToolCallValidationError, ToolCatalog
    from tests.ai.test_agent import _d

    admin = [
        "restart_system",
        "shutdown_system",
        "trigger_system_update",
        "update_setting",
        "install_plugin",
        "configure_plugin",
        "export_backup",
        "remove_board",
        "set_temporary_override",
    ]
    catalog = ToolCatalog([_d(name) for name in ["create_page", "send_message", "ask_user", *admin]]).for_tv("tv")
    for name in admin:
        with pytest.raises(ToolCallValidationError):
            catalog.validate({"op": name})
    assert catalog.validate({"op": "create_page", "args": {"name": "Weather"}}).name == "create_page"
    assert catalog.validate({"op": "send_message", "args": {"text": "Hello"}}).args["board_id"] == "tv"
    with pytest.raises(ToolCallValidationError, match="selected TV board"):
        catalog.validate({"op": "send_message", "args": {"text": "Hello", "board_id": "primary"}})


def test_tv_resume_cannot_execute_an_admin_call_from_client_history():
    from tests.ai.test_agent import FakeBackend, ScriptedProvider, _pending_transcript, _run_turn

    backend = FakeBackend()
    call = {"id": "admin", "name": "restart_system", "args": {}}
    events = _run_turn(
        ScriptedProvider(),
        backend,
        _pending_transcript(call),
        resume={"tool_call_id": "admin", "decision": "approve"},
        interaction_mode="tv",
        target_board={"id": "tv", "device_type": "flagship"},
    )
    assert backend.calls == []
    assert events[-1]["event"] == "error"


def test_tv_turn_retains_questions_and_passes_real_geometry_to_provider():
    from tests.ai.test_agent import USER, FakeBackend, ScriptedProvider, _block, _only, _run_turn, _sse

    provider = ScriptedProvider(
        _sse(
            _block(
                "ask_user",
                {
                    "question": "Which layout?",
                    "options": ["Weather", "Clock"],
                    "allow_free_text": True,
                },
            )
        )
    )
    events = _run_turn(
        provider,
        FakeBackend(),
        USER,
        interaction_mode="tv",
        target_board={
            "id": "tv",
            "device_type": "panel",
            "grid_rows": 18,
            "grid_cols": 45,
        },
    )
    system = provider.messages_of(0)[0]["content"]
    assert "45 columns x 18 rows" in system
    assert "TV INTERACTION" in system
    question = _only(events, "elicitation")[0]
    assert question["requested_schema"]["properties"]["answer"]["enum"] == ["Weather", "Clock"]
    assert question["allow_free_text"] is True
    assert _only(events, "done")[0]["reason"] == "awaiting_input"


def test_tv_destructive_content_change_keeps_approval_gate():
    from tests.ai.test_agent import USER, FakeBackend, ScriptedProvider, _block, _only, _run_turn, _sse

    backend = FakeBackend()
    provider = ScriptedProvider(_sse(_block("delete_page", {"page_id": "p"})))
    events = _run_turn(
        provider,
        backend,
        USER,
        interaction_mode="tv",
        target_board={
            "id": "tv",
            "device_type": "flagship",
        },
    )
    assert backend.calls == []
    assert _only(events, "done")[0]["reason"] == "awaiting_approval"
