"""Rich cells reach an LED board through every send path, not only the engine.

B3 projected the engine's page, silence and trigger sends per output. The
other ways content reaches a board did not, so an LED board lost its
colours and icons whenever it was written from them:

- ``POST /v1/boards/{board}/message`` (``text``, ``lines`` and ``page_id``)
  and ``POST /send-message`` / the MCP ``send_message`` tool, which share
  :func:`src.displays.messages.render_message`;
- the MQTT ``send_message`` command;
- ``POST /templates/render/live`` (the live editor);
- ``POST /pages/{id}/send``, the immediate send of ``POST /active-page`` and
  ``POST /displays/{type}/send``.

For each, a board whose output draws a rich character set gets the frame's
rich cells (and a page or template rendered with extended markup); a
split-flap board's call is byte-identical to before: the same grid from
``text_to_board_array`` and no ``cells`` keyword.
"""

from __future__ import annotations

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.outputs.cells import project_message
from src.text_to_board import text_to_board_array, wrap_message_text
from tests.test_v1_contract import board_client, boards, client  # noqa: F401 - fixtures

LED = BUILTIN_CHARACTER_SETS["led_5x7"]
RICH_TEXT = "{red:HOT} {icon:sun}"


def _rich(mock):
    mock.character_set = LED
    return mock


# --- render_message (POST /send-message, MCP send_message, v1 text) ------------------------


def _render_message(target):
    from src.displays.messages import render_message

    target.render.return_value = (True, True)
    render_message(target, RICH_TEXT, rows=6, cols=22, strategy=None, step_interval_ms=None, step_size=None)
    return target.render.call_args


def test_render_message_sends_a_rich_boards_cells():
    call = _render_message(_rich(Mock()))
    expected = project_message(wrap_message_text(RICH_TEXT, rows=6, cols=22), 6, 22, LED)
    assert call.args[0] == expected.characters
    assert call.kwargs["cells"] == expected.cells


def test_render_message_on_a_split_flap_board_is_unchanged():
    call = _render_message(Mock())
    assert call.args[0] == text_to_board_array(wrap_message_text(RICH_TEXT, rows=6, cols=22), rows=6, cols=22)
    assert "cells" not in call.kwargs


# --- POST /v1/boards/{board}/message ------------------------------------------------------------


def test_v1_text_reaches_a_rich_board_with_cells(client, boards, board_client):  # noqa: F811
    _rich(board_client)
    assert client.post("/v1/boards/primary/message", json={"text": RICH_TEXT}).status_code == 200
    assert board_client.render.call_args.kwargs["cells"] == project_message(RICH_TEXT, 6, 22, LED).cells


def test_v1_lines_reach_a_rich_board_with_cells(client, boards, board_client):  # noqa: F811
    _rich(board_client)
    response = client.post("/v1/boards/primary/message", json={"lines": ["{green:GO}", "{icon:sun}"]})
    assert response.status_code == 200
    expected = project_message("{green:GO}\n{icon:sun}", 6, 22, LED)
    assert board_client.render.call_args.args[0] == expected.characters
    assert board_client.render.call_args.kwargs["cells"] == expected.cells
    assert response.json()["characters"] == expected.characters


def test_v1_lines_on_a_split_flap_board_are_unchanged(client, boards, board_client):  # noqa: F811
    response = client.post("/v1/boards/primary/message", json={"lines": ["{green:GO}", "{icon:sun}"]})
    assert response.status_code == 200
    assert board_client.render.call_args.args[0] == text_to_board_array("{green:GO}\n{icon:sun}", rows=6, cols=22)
    assert "cells" not in board_client.render.call_args.kwargs


def test_v1_page_id_renders_the_page_for_a_rich_board(client, boards, board_client):  # noqa: F811
    from src.pages.service import get_page_service

    _rich(board_client)
    page = client.post(
        "/v1/pages",
        json={"name": "Hot", "type": "template", "device_type": "flagship", "template": ["{{red:HOT}}"]},
    ).json()
    with patch.object(get_page_service(), "preview_page", wraps=get_page_service().preview_page) as preview:
        assert client.post("/v1/boards/primary/message", json={"page_id": page["id"]}).status_code == 200
    assert preview.call_args.kwargs.get("extended_markup") is True
    cells = board_client.render.call_args.kwargs["cells"]
    assert cells[0][0].to_dict() == {"type": "char", "value": "H", "color": "red"}


def test_v1_page_id_on_a_split_flap_board_is_unchanged(client, boards, board_client):  # noqa: F811
    from src.pages.service import get_page_service

    page = client.post(
        "/v1/pages",
        json={"name": "Hot", "type": "template", "device_type": "flagship", "template": ["{{red:HOT}}"]},
    ).json()
    with patch.object(get_page_service(), "preview_page", wraps=get_page_service().preview_page) as preview:
        assert client.post("/v1/boards/primary/message", json={"page_id": page["id"]}).status_code == 200
    assert "extended_markup" not in preview.call_args.kwargs
    assert "cells" not in board_client.render.call_args.kwargs


# --- MQTT send_message --------------------------------------------------------------------------


def _mqtt_send(board_client_mock):
    from src.mqtt.client import MQTTClient
    from src.mqtt.commands import CommandHandler
    from src.mqtt.config import MQTTConfig

    mqtt = MagicMock(spec=MQTTClient)
    mqtt._state_publisher = None
    mqtt.config = MQTTConfig(enabled=True, base_topic="fiestaboard")
    handler = CommandHandler(mqtt, start_display_service=MagicMock(), stop_display_service=MagicMock())
    settings = MagicMock()
    settings.get_board_settings.return_value = MagicMock(
        boards=[{"id": "b1", "name": "Sign", "device_type": "flagship"}]
    )
    settings.get_primary_board_id.return_value = "b1"
    settings.is_paused.return_value = False
    settings.get_transition_settings.return_value = MagicMock(strategy=None, step_interval_ms=None, step_size=None)
    service = MagicMock()
    service.vb_client = board_client_mock
    board_client_mock.send_characters.return_value = (True, True)
    with (
        patch("src.api_server.peek_service", return_value=None),
        patch("src.api_server.get_service", return_value=service),
        patch("src.settings.service.get_settings_service", return_value=settings),
        patch("src.config.Config") as config,
    ):
        config.is_silence_mode_active.return_value = False
        handler.handle("send_message", RICH_TEXT)
    return board_client_mock.send_characters.call_args


def test_mqtt_send_message_sends_a_rich_boards_cells():
    call = _mqtt_send(_rich(MagicMock()))
    expected = project_message(wrap_message_text(RICH_TEXT, rows=6, cols=22), 6, 22, LED)
    assert call.args[0] == expected.characters
    assert call.kwargs["cells"] == expected.cells


def test_mqtt_send_message_on_a_split_flap_board_is_unchanged():
    call = _mqtt_send(MagicMock())
    assert call.args[0] == text_to_board_array(wrap_message_text(RICH_TEXT, rows=6, cols=22), rows=6, cols=22)
    assert "cells" not in call.kwargs


# --- POST /templates/render/live ----------------------------------------------------------------


@pytest.fixture
def live(_isolated_data_dir):
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.settings.service import get_settings_service

    get_settings_service().set_boards([{"id": "sign", "name": "Sign", "device_type": "flagship"}])
    driver = Mock()
    driver.render.return_value = (True, True)
    with patch("src.templates.routes.live_driver", return_value=driver):
        yield TestClient(app), driver


def test_the_live_editor_renders_and_sends_cells_to_a_rich_board(live):
    api, driver = live
    _rich(driver)
    body = api.post("/templates/render/live", json={"template": ["{{red:HOT}}"], "board_id": "sign"}).json()
    assert body["sent_to_board"] is True
    assert body["rendered"].startswith("{red:HOT}")  # rendered with the board's extended markup
    expected = project_message(body["rendered"], 6, 22, LED)
    assert driver.render.call_args.args[0] == expected.characters
    assert driver.render.call_args.kwargs["cells"] == expected.cells


def test_the_live_editor_on_a_split_flap_board_is_unchanged(live):
    api, driver = live
    body = api.post("/templates/render/live", json={"template": ["{{red:HOT}}"], "board_id": "sign"}).json()
    assert not body["rendered"].startswith("{red:HOT}")
    assert driver.render.call_args.args[0] == text_to_board_array(body["rendered"], rows=6, cols=22)
    assert "cells" not in driver.render.call_args.kwargs


# --- POST /pages/{id}/send ----------------------------------------------------------------------


def _page_send(client, board_client_mock):  # noqa: F811
    page = client.post(
        "/v1/pages",
        json={"name": "Hot", "type": "template", "device_type": "flagship", "template": ["{{red:HOT}}"]},
    ).json()
    service = Mock(vb_client=board_client_mock)
    with patch("src.pages.routes.get_service", return_value=service):
        response = client.post(f"/pages/{page['id']}/send", params={"target": "board"})
    assert response.status_code == 200, response.text
    return board_client_mock.render.call_args


def test_sending_a_page_to_a_rich_board_sends_its_cells(client, boards, board_client):  # noqa: F811
    call = _page_send(client, _rich(board_client))
    assert call.kwargs["cells"][0][0].to_dict() == {"type": "char", "value": "H", "color": "red"}


def test_sending_a_page_to_a_split_flap_board_is_unchanged(client, boards, board_client):  # noqa: F811
    call = _page_send(client, board_client)
    assert "cells" not in call.kwargs


# --- PUT /settings/active-page (the immediate send) -------------------------------------------


def _active_page_send(client, board_client_mock):  # noqa: F811
    page = client.post(
        "/v1/pages",
        json={"name": "Hot", "type": "template", "device_type": "flagship", "template": ["{{red:HOT}}"]},
    ).json()
    response = client.put("/settings/active-page", json={"page_id": page["id"]})
    assert response.status_code == 200, response.text
    return board_client_mock.render.call_args


def test_activating_a_page_sends_a_rich_board_its_cells(client, boards, board_client):  # noqa: F811
    call = _active_page_send(client, _rich(board_client))
    assert call.kwargs["cells"][0][0].to_dict() == {"type": "char", "value": "H", "color": "red"}


def test_activating_a_page_on_a_split_flap_board_is_unchanged(client, boards, board_client):  # noqa: F811
    call = _active_page_send(client, board_client)
    assert "cells" not in call.kwargs


# --- POST /displays/{type}/send ------------------------------------------------------------------


def _display_send(client, board_client_mock):  # noqa: F811
    from src.displays.service import DisplayResult

    result = DisplayResult(display_type="demo", formatted="{red:HOT}", raw={}, available=True)
    service = Mock(vb_client=board_client_mock)
    displays = Mock()
    displays.get_display.return_value = result
    with (
        patch("src.displays.routes.get_service", return_value=service),
        patch("src.displays.routes.get_display_service", return_value=displays),
    ):
        response = client.post("/displays/demo/send", params={"target": "board"})
    assert response.status_code == 200, response.text
    return board_client_mock.render.call_args


def test_sending_a_display_to_a_rich_board_sends_its_cells(client, boards, board_client):  # noqa: F811
    call = _display_send(client, _rich(board_client))
    assert call.kwargs["cells"] == project_message("{red:HOT}", 6, 22, LED).cells


def test_sending_a_display_to_a_split_flap_board_is_unchanged(client, boards, board_client):  # noqa: F811
    call = _display_send(client, board_client)
    assert call.args[0] == text_to_board_array("{red:HOT}", rows=6, cols=22)
    assert "cells" not in call.kwargs
