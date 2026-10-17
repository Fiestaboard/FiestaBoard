"""Manual sends respect the silence window unless explicitly forced (issue #1943).

* ``POST /displays/{type}/send`` used to ignore silence entirely; it now
  skips the board write during silence, like every other manual send.
* Both ``POST /displays/{type}/send`` and ``POST /pages/{id}/send`` accept a
  ``force=true`` query param that overrides silence for that one send.
  Pause is never overridden.
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.api_server import app


@pytest.fixture
def client():
    return TestClient(app)


def _display_mocks():
    service = Mock()
    service.vb_client = Mock()
    display_service = Mock()
    result = Mock(available=True, error=None, formatted="HELLO")
    display_service.get_display.return_value = result
    ss = Mock()
    ss.should_send_to_board.return_value = True
    ss.get_output_settings.return_value = Mock(target="board")
    ss.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=None, step_size=None)
    ss.get_board_settings.return_value = Mock(boards=[{"id": "b1", "device_type": "flagship"}])
    return service, display_service, ss


def _post_display(client, *, silenced, paused=False, query=""):
    service, display_service, ss = _display_mocks()

    async def fake_send(fn, *args, **kwargs):
        return (True, True)

    with (
        patch("src.displays.routes.get_service", return_value=service),
        patch("src.displays.routes.get_display_service", return_value=display_service),
        patch("src.displays.routes.get_settings_service", return_value=ss),
        patch("src.displays.routes._silence_active", return_value=silenced),
        patch("src.displays.routes._board_is_paused", return_value=paused),
        patch("src.displays.routes.run_board_send", side_effect=fake_send) as send,
    ):
        response = client.post(f"/displays/weather/send{query}")
    return response, send


class TestDisplaySendSilence:
    def test_silence_blocks_board_write_by_default(self, client):
        response, send = _post_display(client, silenced=True)
        assert response.status_code == 200
        assert response.json()["sent_to_board"] is False
        send.assert_not_called()

    def test_force_overrides_silence(self, client):
        response, send = _post_display(client, silenced=True, query="?force=true")
        assert response.status_code == 200
        assert response.json()["sent_to_board"] is True
        send.assert_called_once()

    def test_force_does_not_override_pause(self, client):
        response, send = _post_display(client, silenced=True, paused=True, query="?force=true")
        assert response.status_code == 200
        assert response.json()["sent_to_board"] is False
        assert response.json()["paused"] is True
        send.assert_not_called()

    def test_not_silenced_sends_normally(self, client):
        response, send = _post_display(client, silenced=False)
        assert response.json()["sent_to_board"] is True
        send.assert_called_once()


def _post_page(client, *, silenced, query=""):
    service = Mock()
    service.vb_client = Mock()
    service.vb_client.render.return_value = (True, True)
    page = Mock(
        transition_strategy=None, transition_interval_ms=None, transition_step_size=None, device_type="flagship"
    )
    page_service = Mock()
    page_service.get_page.return_value = page
    page_service.preview_page.return_value = Mock(available=True, error=None, formatted="HI")
    ss = Mock()
    ss.should_send_to_board.return_value = True
    ss.get_output_settings.return_value = Mock(target="board")
    ss.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=None, step_size=None)
    with (
        patch("src.pages.routes.get_service", return_value=service),
        patch("src.pages.routes.get_page_service", return_value=page_service),
        patch("src.pages.routes.get_settings_service", return_value=ss),
        patch("src.pages.routes._silence_active", return_value=silenced),
        patch("src.pages.routes._board_is_paused", return_value=False),
        patch("src.pages.routes.geometry_of", return_value=("flagship", None, None, None)),
        patch("src.pages.routes.resolve_dimensions", return_value=Mock(rows=6, cols=22)),
        patch("src.pages.routes.text_to_board_array", return_value=[[0] * 22] * 6),
    ):
        response = client.post(f"/pages/p1/send{query}")
    return response, service.vb_client.render


class TestPageSendSilence:
    def test_silence_blocks_board_write_by_default(self, client):
        response, render = _post_page(client, silenced=True)
        assert response.status_code == 200, response.text
        assert response.json()["sent_to_board"] is False
        render.assert_not_called()

    def test_force_overrides_silence(self, client):
        response, render = _post_page(client, silenced=True, query="?force=true")
        assert response.status_code == 200, response.text
        assert response.json()["sent_to_board"] is True
        render.assert_called_once()
