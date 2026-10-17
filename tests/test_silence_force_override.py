"""Manual sends respect the silence window unless explicitly overridden (issue #1943).

* ``POST /displays/{type}/send`` used to ignore silence entirely; it now
  skips the board write during silence, like every other manual send.
* Both ``POST /displays/{type}/send`` and ``POST /pages/{id}/send`` accept an
  ``override_silence=true`` query param that overrides silence for that one
  send. The #2252 name for it, ``force``, is gone: one override name on every
  surface, and v1's ``force`` keeps meaning "resend unchanged content".
  Pause is never overridden, and both flags are reported truthfully.
* During silence without the override, the page or display is held as an
  intent when the board's schedule holds sends (``held``, issue #1944).
"""

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src import silence_queue
from src.api_server import app
from src.silence_queue import HeldSend


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


def _holds(enabled):
    from src.config import Config

    real = Config.silence_config_for.__func__

    def config_for(cls, board_id=None):
        return {**real(cls, board_id), "show_queued_on_exit": enabled}

    return patch.object(Config, "silence_config_for", classmethod(config_for))


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


def _post_display(client, *, silenced, paused=False, query="", holds=False):
    service, display_service, ss = _display_mocks()

    async def fake_send(fn, *args, **kwargs):
        return (True, True)

    with (
        patch("src.displays.routes.get_service", return_value=service),
        patch("src.displays.routes.get_display_service", return_value=display_service),
        patch("src.displays.routes.get_settings_service", return_value=ss),
        patch("src.board_guards._silence_active", return_value=silenced),
        patch("src.board_guards.resolve_board_id", side_effect=lambda b: b or "b1"),
        patch("src.displays.routes._board_is_paused", return_value=paused),
        patch("src.displays.routes.run_board_send", side_effect=fake_send) as send,
        _holds(holds),
    ):
        response = client.post(f"/displays/weather/send{query}")
    return response, send


class TestDisplaySendSilence:
    def test_silence_blocks_board_write_by_default(self, client):
        response, send = _post_display(client, silenced=True)
        assert response.status_code == 200
        body = response.json()
        assert (body["sent_to_board"], body["silenced"], body["held"]) == (False, True, False)
        send.assert_not_called()

    def test_override_silence_overrides_silence(self, client):
        response, send = _post_display(client, silenced=True, query="?override_silence=true")
        assert response.status_code == 200
        assert response.json()["sent_to_board"] is True
        assert response.json()["silenced"] is False
        send.assert_called_once()

    def test_the_old_force_name_no_longer_overrides_silence(self, client):
        response, send = _post_display(client, silenced=True, query="?force=true")
        assert response.json()["sent_to_board"] is False
        assert response.json()["silenced"] is True
        send.assert_not_called()

    def test_override_does_not_override_pause(self, client):
        response, send = _post_display(client, silenced=True, paused=True, query="?override_silence=true")
        assert response.status_code == 200
        assert response.json()["sent_to_board"] is False
        assert response.json()["paused"] is True
        send.assert_not_called()

    def test_silenced_and_paused_reports_both(self, client):
        response, send = _post_display(client, silenced=True, paused=True)
        body = response.json()
        assert (body["silenced"], body["paused"]) == (True, True)
        send.assert_not_called()

    def test_not_silenced_sends_normally(self, client):
        response, send = _post_display(client, silenced=False)
        assert response.json()["sent_to_board"] is True
        assert response.json()["silenced"] is False
        send.assert_called_once()

    def test_silenced_display_is_held_when_holds_are_on(self, client):
        response, send = _post_display(client, silenced=True, holds=True)
        assert response.json()["held"] is True
        held = silence_queue.peek("b1")
        assert (held.kind, held.payload) == ("display", "weather")
        send.assert_not_called()

    def test_an_overriding_display_send_discards_the_primary_boards_held_entry(self, client):
        silence_queue.hold(HeldSend.text("NIGHT", board_id="b1"))
        _post_display(client, silenced=True, query="?override_silence=true")
        assert silence_queue.peek("b1") is None


def _post_page(client, *, silenced, query="", holds=False, paused=False):
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
        patch("src.board_guards._silence_active", return_value=silenced),
        patch("src.board_guards.resolve_board_id", side_effect=lambda b: b or "b1"),
        patch("src.pages.routes._board_is_paused", return_value=paused),
        patch("src.pages.routes.geometry_of", return_value=("flagship", None, None, None)),
        patch("src.pages.routes.resolve_dimensions", return_value=Mock(rows=6, cols=22)),
        patch("src.pages.routes.text_to_board_array", return_value=[[0] * 22] * 6),
        _holds(holds),
    ):
        response = client.post(f"/pages/p1/send{query}")
    return response, service.vb_client.render


class TestPageSendSilence:
    def test_silence_blocks_board_write_by_default(self, client):
        response, render = _post_page(client, silenced=True)
        assert response.status_code == 200, response.text
        body = response.json()
        assert (body["sent_to_board"], body["silenced"]) == (False, True)
        render.assert_not_called()

    def test_override_silence_overrides_silence(self, client):
        response, render = _post_page(client, silenced=True, query="?override_silence=true")
        assert response.status_code == 200, response.text
        assert response.json()["sent_to_board"] is True
        assert response.json()["silenced"] is False
        render.assert_called_once()

    def test_the_old_force_name_no_longer_overrides_silence(self, client):
        response, render = _post_page(client, silenced=True, query="?force=true")
        assert response.json()["sent_to_board"] is False
        render.assert_not_called()

    def test_pause_still_wins_over_the_override(self, client):
        response, render = _post_page(client, silenced=True, paused=True, query="?override_silence=true")
        body = response.json()
        assert (body["sent_to_board"], body["paused"], body["silenced"]) == (False, True, False)
        render.assert_not_called()

    def test_silenced_page_is_held_as_the_page(self, client):
        response, render = _post_page(client, silenced=True, holds=True)
        assert response.json()["held"] is True
        held = silence_queue.peek("b1")
        assert (held.kind, held.payload) == ("page", "p1")
        render.assert_not_called()
