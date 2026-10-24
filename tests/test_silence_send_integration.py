"""Manual writes obey silence without losing previews, pause or newer intent."""

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src import silence_queue
from src.config_manager import get_config_manager
from src.pages.models import PageCreate
from src.pages.service import get_page_service
from src.settings.service import get_settings_service
from tests.fake_clock import FakeClock, install_fake_time_service


@pytest.fixture
def sends(monkeypatch):
    from src.api_server import app

    settings = get_settings_service()
    boards = settings.set_boards(
        [
            {"name": "Primary", "device_type": "flagship"},
            {"name": "Secondary", "device_type": "note"},
        ]
    ).boards
    settings.set_output_target("both")
    pages = get_page_service()
    page = pages.create_page(PageCreate(name="Morning", type="template", template=["HELLO"]))
    clients = {b["id"]: Mock() for b in boards}
    for client in clients.values():
        client.render.return_value = (True, True)
        client.send_characters.return_value = (True, True)
    service = Mock()
    service.vb_client = clients[boards[0]["id"]]
    service.get_board_client.side_effect = clients.get
    monkeypatch.setattr("src.api_server.get_service", lambda: service)
    monkeypatch.setattr("src.api_server.peek_service", lambda: service)
    monkeypatch.setattr("src.pages.routes.get_service", lambda: service)
    monkeypatch.setattr("src.displays.routes.get_service", lambda: service)
    monkeypatch.setattr("src.templates.routes.board_client_from_board_dict", lambda b: clients[b["id"]])
    monkeypatch.setattr(
        "src.displays.routes.get_display_service",
        lambda: SimpleNamespace(get_display=lambda _: SimpleNamespace(available=True, formatted="PLUGIN", error=None)),
    )
    cm = get_config_manager()
    cm.set_feature(
        "silence_schedule",
        {
            "enabled": True,
            "start_time": "22:00+00:00",
            "end_time": "07:00+00:00",
            "show_queued_on_exit": True,
            "by_board": {},
        },
    )
    clock = FakeClock(datetime(2026, 10, 24, 23, 30, tzinfo=UTC))
    install_fake_time_service(monkeypatch, clock)
    return SimpleNamespace(
        http=TestClient(app),
        settings=settings,
        boards=boards,
        clients=clients,
        page=page,
        clock=clock,
        config=cm,
        service=service,
    )


@pytest.mark.parametrize("secondary", [False, True])
@pytest.mark.parametrize("surface", ["legacy", "v1", "ops", "mqtt"])
def test_message_is_held_for_only_its_board(sends, surface, secondary):
    bid = sends.boards[int(secondary)]["id"]
    if surface == "legacy":
        response = sends.http.post("/send-message", json={"text": "LATER", "board_id": bid})
    elif surface == "v1":
        response = sends.http.post(f"/v1/boards/{bid}/message", json={"text": "LATER", "force": True})
    elif surface == "ops":
        from src.ops.executors import send_message

        result = send_message("LATER", board_id=bid)
        assert result.get("held") is True
    else:
        from src.mqtt.commands import CommandHandler

        CommandHandler(Mock())._handle_send_message(json.dumps({"message": "LATER", "board_id": bid}))
    if surface in ("legacy", "v1"):
        assert response.status_code == 202, response.text
        assert response.json()["held"] is True
        assert response.json()["sent"] is False
        assert response.json()["ends_at_utc"] == "2026-10-25T07:00:00+00:00"
    assert silence_queue.peek(bid).payload == "LATER"
    assert silence_queue.peek(sends.boards[int(not secondary)]["id"]) is None
    for client in sends.clients.values():
        client.render.assert_not_called()
        client.send_characters.assert_not_called()


@pytest.mark.parametrize("surface", ["active", "page", "display", "live", "v1active"])
def test_selection_and_preview_are_truthful_during_silence(sends, surface):
    bid = sends.boards[0]["id"]
    routes = {
        "active": ("put", "/settings/active-page", {"page_id": sends.page.id}),
        "v1active": ("put", "/v1/boards/primary/active-page", {"page_id": sends.page.id}),
        "page": ("post", f"/pages/{sends.page.id}/send", {}),
        "display": ("post", "/displays/weather/send", {}),
        "live": ("post", "/templates/render/live", {"template": ["EDITING"]}),
    }
    method, url, body = routes[surface]
    response = getattr(sends.http, method)(url, json=body)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("silenced") is True
    assert data.get("sent_to_board", data.get("sent")) is False
    sends.clients[bid].render.assert_not_called()
    sends.clients[bid].send_characters.assert_not_called()
    if surface in ("active", "v1active"):
        assert sends.settings.get_active_page_id() == sends.page.id
    assert silence_queue.peek(bid) is not None


@pytest.mark.parametrize("surface", ["legacy", "v1"])
@pytest.mark.parametrize("paused", [False, True])
def test_explicit_override_sends_only_when_not_paused_and_supersedes_old(sends, surface, paused):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("OLD", board_id=bid)
    silence_queue.hold(old)
    sends.settings.set_paused(paused, board_id=bid)
    url = "/send-message" if surface == "legacy" else "/v1/boards/primary/message"
    response = sends.http.post(url, json={"text": "NOW", "override_silence": True})
    assert response.status_code == (409 if paused else 200), response.text
    assert silence_queue.peek(bid) == (old if paused else None)
    if paused:
        sends.clients[bid].render.assert_not_called()
    else:
        assert response.json()["sent"] is True


@pytest.mark.parametrize(
    "body",
    [
        {"characters": [[99]]},
        {"characters": [[1]]},
        {"text": "X", "lines": ["Y"]},
        {"text": "X", "override_silence": "false"},
    ],
)
def test_invalid_v1_write_preserves_prior_intent(sends, body):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    response = sends.http.post("/v1/boards/primary/message", json=body)
    assert response.status_code in (400, 422)
    assert silence_queue.peek(bid) == old


def test_unknown_target_never_holds(sends):
    response = sends.http.post("/send-message", json={"text": "X", "board_id": "missing"})
    assert response.status_code == 404
    assert silence_queue.peek("missing") is None


def test_older_completion_cannot_discard_newer_intent(sends):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("OLD", board_id=bid)
    newer = silence_queue.HeldSend.text("NEW", board_id=bid)
    silence_queue.hold(old)

    def deliver(*args, **kwargs):
        silence_queue.hold(newer)
        return True, True

    sends.clients[bid].render.side_effect = deliver
    response = sends.http.post("/send-message", json={"text": "NOW", "override_silence": True})
    assert response.status_code == 200
    assert silence_queue.peek(bid) == newer


def test_conditional_discard_is_atomic(sends):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("OLD", board_id=bid)
    newer = silence_queue.HeldSend.text("NEW", board_id=bid)
    silence_queue.hold(newer)
    assert "expected" in __import__("inspect").signature(silence_queue.discard).parameters
    assert silence_queue.discard(bid, expected=old) is False
    assert silence_queue.peek(bid) == newer
    assert silence_queue.discard(bid, expected=newer) is True


@pytest.mark.parametrize("surface", ["page", "live", "active"])
def test_override_requires_a_real_json_boolean_before_queue_mutation(sends, surface):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    method, url, body = {
        "page": ("post", f"/pages/{sends.page.id}/send", {}),
        "live": ("post", "/templates/render/live", {"template": ["X"]}),
        "active": ("put", "/settings/active-page", {"page_id": sends.page.id}),
    }[surface]
    response = getattr(sends.http, method)(url, json={**body, "override_silence": "false"})
    assert response.status_code == 422
    assert silence_queue.peek(bid) == old


@pytest.mark.parametrize("message", [12, ["X"], {"text": "X"}])
def test_malformed_mqtt_message_does_not_replace_held(sends, message):
    from src.mqtt.commands import CommandHandler

    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    CommandHandler(Mock())._handle_send_message(json.dumps({"message": message, "board_id": bid}))
    assert silence_queue.peek(bid) == old


def test_mcp_tools_hold_then_explicitly_wake_with_real_executor(sends):
    from src.mcp_server import _build_mcp_server
    from tests.test_mcp_server import _call_tool

    bid = sends.boards[0]["id"]
    mcp = _build_mcp_server()
    response = _call_tool(mcp, "send_message", text="MCP LATER", board_id=bid)
    assert response["held"] is True
    assert silence_queue.peek(bid).payload == "MCP LATER"
    response = _call_tool(mcp, "set_active_page", page_id=sends.page.id, board_id=bid)
    assert response["silenced"] is True
    assert silence_queue.peek(bid).kind == "page"
    response = _call_tool(mcp, "send_message", text="MCP NOW", board_id=bid, override_silence=True)
    assert response["status"] == "success"
    assert silence_queue.peek(bid) is None


def test_force_alone_never_bypasses_silence_when_holding_is_disabled(sends):
    sends.config.set_feature("silence_schedule", {"show_queued_on_exit": False})
    response = sends.http.post("/v1/boards/primary/message", json={"text": "X", "force": True})
    assert response.status_code == 409
    sends.clients[sends.boards[0]["id"]].render.assert_not_called()


def _write_preview(sends, surface, *, override=True):
    method, url, body = {
        "active": ("put", "/settings/active-page", {"page_id": sends.page.id}),
        "page": ("post", f"/pages/{sends.page.id}/send", {}),
        "display": ("post", f"/displays/weather/send?override_silence={str(override).lower()}", {}),
        "live": ("post", "/templates/render/live", {"template": ["EDITING"]}),
    }[surface]
    return getattr(sends.http, method)(url, json={**body, "override_silence": override})


@pytest.mark.parametrize("surface", ["active", "page", "display", "live"])
@pytest.mark.parametrize("state", ["success", "failed", "paused", "throttled"])
def test_preview_override_only_successful_delivery_supersedes(sends, surface, state):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    sends.settings.set_paused(state == "paused", board_id=bid)
    if state in ("failed", "throttled"):
        outcome = (state == "throttled", False)
        sends.clients[bid].render.return_value = outcome
        sends.clients[bid].send_characters.return_value = outcome
    response = _write_preview(sends, surface)
    if state == "success":
        assert response.status_code == 200, response.text
        assert response.json()["sent_to_board"] is True
        assert silence_queue.peek(bid) is None
    else:
        assert silence_queue.peek(bid) == old
        if response.status_code == 200:
            assert response.json()["sent_to_board"] is False
        else:
            assert response.status_code == 500
    if state == "paused":
        sends.clients[bid].render.assert_not_called()
        sends.clients[bid].send_characters.assert_not_called()


@pytest.mark.parametrize("surface", ["active", "page", "display", "live"])
def test_preview_opt_out_blocks_without_replacing_existing_intent(sends, surface):
    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    sends.config.set_feature("silence_schedule", {"show_queued_on_exit": False})
    response = _write_preview(sends, surface, override=False)
    assert response.status_code == 200
    assert response.json()["silenced"] is True
    assert response.json()["held"] is False
    assert response.json()["sent_to_board"] is False
    assert silence_queue.peek(bid) == old


@pytest.mark.parametrize("surface", ["legacy", "v1", "ops", "mqtt"])
def test_successful_daytime_message_supersedes_old_intent(sends, surface):
    from src.mqtt.commands import CommandHandler
    from src.ops.executors import send_message

    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("OLD", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    if surface == "legacy":
        assert sends.http.post("/send-message", json={"text": "NEW"}).status_code == 200
    elif surface == "v1":
        assert sends.http.post("/v1/boards/primary/message", json={"text": "NEW"}).status_code == 200
    elif surface == "ops":
        assert send_message("NEW")["status"] == "success"
    else:
        CommandHandler(Mock())._handle_send_message("NEW")
    assert silence_queue.peek(bid) is None


@pytest.mark.parametrize(
    "body,kind",
    [
        ({"lines": ["ROWS"]}, "lines"),
        ({"fill": 4}, "grid"),
        ({"template": ["FIXED"]}, "grid"),
        ({"page_id": "PAGE"}, "page"),
    ],
)
def test_v1_retains_typed_intent_for_content_forms(sends, body, kind):
    body = {**body}
    if "page_id" in body:
        body["page_id"] = sends.page.id
    response = sends.http.post("/v1/boards/primary/message", json=body)
    assert response.status_code == 202, response.text
    assert silence_queue.peek(sends.boards[0]["id"]).kind == kind


def test_mqtt_active_selection_is_saved_and_held_without_engine_wake(sends):
    from src.mqtt.commands import CommandHandler

    bid = sends.boards[0]["id"]
    handler = CommandHandler(Mock())
    handler._handle_active_page(json.dumps({"page": sends.page.name, "board_id": bid}))
    assert sends.settings.get_active_page_id(board_id=bid) == sends.page.id
    assert silence_queue.peek(bid).payload == sends.page.id
    sends.service.check_and_send_for_board.assert_not_called()


@pytest.mark.parametrize("prior_hold", [False, True])
def test_mqtt_ui_only_selection_preserves_queue(sends, prior_hold):
    from src.mqtt.commands import CommandHandler

    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid) if prior_hold else None
    if old:
        silence_queue.hold(old)
    sends.settings.set_output_target("ui")
    CommandHandler(Mock())._handle_active_page(json.dumps({"page": sends.page.name, "board_id": bid}))
    assert sends.settings.get_active_page_id(board_id=bid) == sends.page.id
    assert silence_queue.peek(bid) == old
    sends.clients[bid].render.assert_not_called()
    sends.service.check_and_send_for_board.assert_not_called()


@pytest.mark.parametrize("collection", [False, True])
def test_mqtt_incompatible_selection_preserves_previous_intent(sends, collection):
    from src.collections.models import CollectionCreate
    from src.collections.service import get_collection_service
    from src.mqtt.commands import CommandHandler

    bid = sends.boards[1]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    before = sends.settings.get_active_page_id(board_id=bid)
    name = sends.page.name
    if collection:
        item = get_collection_service().create_collection(CollectionCreate(name="Large", page_ids=[sends.page.id]))
        name = f"Collection: {item.name}"
    CommandHandler(Mock())._handle_active_page(json.dumps({"page": name, "board_id": bid}))
    assert silence_queue.peek(bid) == old
    assert sends.settings.get_active_page_id(board_id=bid) == before
    sends.clients[bid].render.assert_not_called()
    sends.service.check_and_send_for_board.assert_not_called()


def test_mqtt_daytime_selection_supersedes_older_held_message(sends):
    from src.mqtt.commands import CommandHandler

    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("OLD", board_id=bid))
    sends.clock.set(datetime(2026, 10, 25, 8, tzinfo=UTC))
    CommandHandler(Mock())._handle_active_page(json.dumps({"page": sends.page.name, "board_id": bid}))
    assert silence_queue.peek(bid) is None
    from tests.helpers import decode_board_rows

    assert decode_board_rows(sends.clients[bid].render.call_args.args[0])[0].strip() == "HELLO"


def test_page_query_override_wins_over_body(sends):
    response = sends.http.post(f"/pages/{sends.page.id}/send?override_silence=false", json={"override_silence": True})
    assert response.status_code == 200
    assert response.json()["silenced"] is True
    sends.clients[sends.boards[0]["id"]].render.assert_not_called()


@pytest.mark.parametrize("surface", ["legacy", "v1", "ops", "mqtt", "active", "page", "display", "live"])
def test_newer_intent_queued_during_explicit_write_survives(sends, surface):
    from src.mqtt.commands import CommandHandler
    from src.ops.executors import send_message

    bid = sends.boards[0]["id"]
    silence_queue.hold(silence_queue.HeldSend.text("OLD", board_id=bid))
    newer = silence_queue.HeldSend.text("NEWEST", board_id=bid)

    def deliver(*args, **kwargs):
        silence_queue.hold(newer)
        return True, True

    sends.clients[bid].render.side_effect = deliver
    sends.clients[bid].send_characters.side_effect = deliver
    if surface == "legacy":
        response = sends.http.post("/send-message", json={"text": "NOW", "override_silence": True})
    elif surface == "v1":
        response = sends.http.post("/v1/boards/primary/message", json={"text": "NOW", "override_silence": True})
    elif surface == "ops":
        assert send_message("NOW", override_silence=True)["status"] == "success"
    elif surface == "mqtt":
        CommandHandler(Mock())._handle_send_message(json.dumps({"message": "NOW", "override_silence": True}))
    else:
        response = _write_preview(sends, surface)
    if surface not in ("ops", "mqtt"):
        assert response.status_code == 200, response.text
    assert silence_queue.peek(bid) == newer


@pytest.mark.parametrize("args", [{"text": []}, {"text": "BAD", "override_silence": "false"}])
def test_canonical_operation_rejects_malformed_send_without_mutation(sends, args):
    from src.ops.registry import execute_sync

    bid = sends.boards[0]["id"]
    old = silence_queue.HeldSend.text("KEEP", board_id=bid)
    silence_queue.hold(old)
    result = execute_sync("send_message", args)
    assert result["status"] == "error"
    assert silence_queue.peek(bid) == old
    sends.clients[bid].render.assert_not_called()


def test_held_legacy_response_keeps_successor_headers(sends):
    response = sends.http.post("/send-message", json={"text": "LATER"})
    assert response.status_code == 202
    assert response.headers.get("deprecation") == "true"
    assert response.headers.get("link") == '</api/v1/boards/{board}/message>; rel="successor-version"'
    assert "sunset" not in response.headers
