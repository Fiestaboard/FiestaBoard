"""Offline regression contracts for the MCP workflow audit."""

from unittest.mock import AsyncMock

import pytest

from tests import test_mcp_state_effects as sibling
from tests.test_mcp_state_effects import call, call_expect_error

mcp = sibling.mcp
services = sibling.services
two_boards = sibling.two_boards
engine = sibling.engine


def test_selecting_a_page_preserves_the_send_failure(mcp, monkeypatch):
    monkeypatch.setattr(
        "src.settings.routes.set_active_page",
        AsyncMock(
            return_value={
                "page_id": "art",
                "board_id": "matrix",
                "sent_to_board": False,
                "paused": False,
                "error": "Canvas render failed",
                "warnings": [],
            }
        ),
    )
    message = call_expect_error(mcp, "set_active_page", page_id="art", board_id="matrix")
    assert "selection was saved" in message and "Canvas render failed" in message


def test_changing_quiet_hours_keeps_existing_mode_and_indicator(mcp, services, two_boards):
    initial = {
        "enabled": True,
        "start_time": "22:00+00:00",
        "end_time": "07:00+00:00",
        "mode": "indicator",
        "indicator_text": "QUIET",
    }
    call(mcp, "update_setting", category="silence_schedule", values=initial)
    call(
        mcp,
        "update_setting",
        category="silence_schedule",
        values={
            "enabled": True,
            "start_time": "23:00+00:00",
            "end_time": "07:00+00:00",
        },
    )
    stored = services["config"].get_feature("silence_schedule")
    assert stored["mode"] == "indicator", stored
    assert stored["indicator_text"] == "QUIET", stored


def test_disabling_quiet_hours_needs_only_enabled(mcp, services, two_boards):
    call(
        mcp,
        "update_setting",
        category="silence_schedule",
        values={
            "enabled": True,
            "start_time": "22:00+00:00",
            "end_time": "07:00+00:00",
        },
    )
    call(mcp, "update_setting", category="silence_schedule", values={"enabled": False})
    assert services["config"].get_feature("silence_schedule")["enabled"] is False


@pytest.mark.parametrize("board_id", [None, "board-note"])
def test_enabling_queued_replay_persists(mcp, services, two_boards, board_id):
    from src.config import resolve_silence_schedule

    values = {
        "enabled": True,
        "start_time": "22:00+00:00",
        "end_time": "07:00+00:00",
        "show_queued_on_exit": True,
    }
    if board_id:
        values["board_id"] = board_id
    result = call(mcp, "update_setting", category="silence_schedule", values=values)
    assert result["status"] == "success"
    feature = services["config"].get_feature("silence_schedule")
    assert resolve_silence_schedule(feature, board_id)["show_queued_on_exit"] is True, feature


def test_blocked_mcp_message_is_queued_when_replay_is_enabled(mcp, engine, monkeypatch):
    from src import silence_queue

    silence_queue.clear()
    monkeypatch.setattr("src.config.Config.is_silence_mode_active", lambda _board_id=None: True)
    monkeypatch.setattr("src.config.Config.silence_config_for", lambda _board_id=None: {"show_queued_on_exit": True})
    try:
        result = call(mcp, "send_message", text="HELLO", board_id="board-main")
        assert result["status"] == "blocked"
        assert engine.vb_client.rendered == []
        held = silence_queue.peek("board-main")
        assert held is not None and held.kind == "text" and held.payload == "HELLO"
    finally:
        silence_queue.clear()


def test_mcp_http_page_roundtrip_and_domain_errors(services, two_boards):
    """Exercise published JSON-RPC rather than only the registered functions."""
    from starlette.testclient import TestClient

    from src.mcp_server import build_streamable_http_app

    app = build_streamable_http_app()
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://localhost") as client:

        def rpc(method, params):
            response = client.post(
                "/",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params,
                },
            )
            assert response.status_code == 200, response.text
            payload = response.json()
            assert "error" not in payload, payload
            return payload["result"]

        initialized = rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "audit", "version": "1"},
            },
        )
        assert initialized["serverInfo"]["name"] == "FiestaBoard"
        tools = rpc("tools/list", {})["tools"]
        assert any(tool["name"] == "create_page" for tool in tools)
        created = rpc(
            "tools/call",
            {
                "name": "create_page",
                "arguments": {
                    "name": "Wire Art",
                    "template_lines": ["HELLO"],
                },
            },
        )
        assert not created.get("isError")
        page_id = created["structuredContent"]["page_id"]
        read = rpc("tools/call", {"name": "get_page", "arguments": {"page_id": page_id}})
        assert read["structuredContent"]["name"] == "Wire Art"
        resources = rpc("resources/list", {})["resources"]
        assert any(resource["uri"] == "fiestaboard://pages" for resource in resources)
        resource = rpc("resources/read", {"uri": "fiestaboard://pages"})
        assert "Wire Art" in resource["contents"][0]["text"]
        error = rpc("tools/call", {"name": "get_page", "arguments": {"page_id": "missing"}})
        assert error["isError"] is True
        assert "not found" in error["content"][0]["text"]
