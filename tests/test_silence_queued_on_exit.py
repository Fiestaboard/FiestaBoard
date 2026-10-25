"""Issue #1944: show the send held during silence when the window ends.

Two halves:

* **Holding.** With the board's ``show_queued_on_exit`` on, a write silence
  refuses is held as a typed intent instead (``src/silence_queue.py``) — from
  every surface, not only the deprecated ``/send-message``. With it off each
  surface refuses exactly as before.
* **Delivering.** The display engine paints the held send on the first tick
  outside the window — text word-wrapped to the board, a page or display
  rendered fresh — and forgets it only once the send lands. A board that is
  paused or UI-only when the window ends drops it instead of waiting.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock, Mock, patch

import pytest

from src import silence_queue
from src.config import resolve_silence_schedule
from src.main import DisplayService
from src.mqtt.commands import CommandHandler
from src.silence_queue import HeldSend
from tests.silence_helpers import silenced
from tests.test_silence_mode_display import TestSilenceModeDispatch as _Dispatch
from tests.test_silence_mode_display import _decode_board_text


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


@pytest.fixture
def service():
    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.send_characters.return_value = (True, True)
    svc.vb_client.render.return_value = (True, True)
    return svc


def test_show_queued_on_exit_defaults_off():
    assert resolve_silence_schedule({"enabled": True})["show_queued_on_exit"] is False


def test_show_queued_on_exit_resolves_per_board():
    feature = {"enabled": True, "by_board": {"b1": {"show_queued_on_exit": True}}}
    assert resolve_silence_schedule(feature, "b1")["show_queued_on_exit"] is True
    assert resolve_silence_schedule(feature, "b2")["show_queued_on_exit"] is False


# ---------------------------------------------------------------------------
# Holding: MQTT / Home Assistant (the REST and MCP surfaces are covered in
# test_v1_message_override_silence.py and test_silence_force_override.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def mqtt_handler():
    return CommandHandler(MagicMock(), start_display_service=MagicMock(), stop_display_service=MagicMock())


@pytest.fixture
def mqtt_board():
    """A primary board 'b1' whose client records sends."""
    client = MagicMock()
    client.send_characters.return_value = (True, True)
    service = MagicMock()
    service.vb_client = client
    service.get_board_client.return_value = client
    settings = MagicMock()
    settings.get_primary_board_id.return_value = "b1"
    settings.is_paused.return_value = False
    settings.get_board_settings.return_value = MagicMock(boards=[{"id": "b1", "device_type": "flagship"}])
    settings.get_transition_settings.return_value = MagicMock(strategy=None, step_interval_ms=None, step_size=None)
    with (
        patch("src.api_server.get_service", return_value=service),
        patch("src.settings.service.get_settings_service", return_value=settings),
        patch("src.board_guards.get_settings_service", return_value=settings),
    ):
        yield client


@pytest.mark.parametrize("payload", ["GOOD MORNING", json.dumps({"message": "GOOD MORNING"})])
def test_mqtt_send_during_silence_is_held_when_holds_are_on(mqtt_handler, mqtt_board, payload):
    with silenced(holds=True):
        mqtt_handler.handle("send_message", payload)
    mqtt_board.send_characters.assert_not_called()
    held = silence_queue.peek("b1")
    assert (held.kind, held.payload) == ("text", "GOOD MORNING")


@pytest.mark.parametrize("payload", ["GOOD MORNING", json.dumps({"message": "GOOD MORNING"})])
def test_mqtt_send_during_silence_is_dropped_when_holds_are_off(mqtt_handler, mqtt_board, payload):
    with silenced(holds=False):
        mqtt_handler.handle("send_message", payload)
    mqtt_board.send_characters.assert_not_called()
    assert silence_queue.peek("b1") is None


def test_mqtt_json_override_silence_writes_and_discards(mqtt_handler, mqtt_board):
    silence_queue.hold(HeldSend.text("NIGHT", board_id="b1"))
    with silenced(holds=True):
        mqtt_handler.handle("send_message", json.dumps({"message": "WAKE UP", "override_silence": True}))
    mqtt_board.send_characters.assert_called_once()
    assert silence_queue.peek("b1") is None


def test_mqtt_plain_payload_line_break_escape_is_held_as_a_newline(mqtt_handler, mqtt_board):
    with silenced(holds=True):
        mqtt_handler.handle("send_message", "GOOD\\nMORNING")
    assert silence_queue.peek("b1").payload == "GOOD\nMORNING"


# ---------------------------------------------------------------------------
# Delivering: the display engine
# ---------------------------------------------------------------------------


class TestExitDelivery:
    def _tick(
        self,
        service,
        *,
        enabled=True,
        ticks=1,
        exiting=True,
        device_type="note",
        paused=False,
        ui_only=False,
        preview=None,
    ):
        if exiting:
            service._last_silence_mode_active = True
        _, page_service, settings, config = _Dispatch()._patch_common(mode="freeze", silence_active=False)
        if preview is not None:
            page_service.preview_page.side_effect = preview
        settings.get_board_settings.return_value = Mock(boards=[{"id": "b1", "device_type": device_type}])
        settings.get_primary_board_id.return_value = "b1"
        settings.consume_temporary_override.return_value = None
        settings.is_paused.return_value = paused
        settings.should_send_to_board.return_value = not ui_only
        config.silence_config_for.return_value = {
            **config.silence_config_for.return_value,
            "show_queued_on_exit": enabled,
        }
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch("src.main.get_schedule_service"),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            results = [service.check_and_send_active_page() for _ in range(ticks)]
        return results[0], page_service

    def _shown(self, service):
        args, _ = service.vb_client.render.call_args
        return _decode_board_text(args[0])

    def test_held_message_is_shown_when_silence_ends(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        self._tick(service)
        assert self._shown(service) == "GOOD MORNING"
        assert silence_queue.peek("b1") is None

    def test_held_message_ignored_when_option_off(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        self._tick(service, enabled=False)
        for call in service.vb_client.render.call_args_list:
            assert "GOOD MORNING" not in _decode_board_text(call.args[0])

    def test_held_message_persists_past_the_next_tick(self, service):
        # Like any manual send (#1794), the delivered message stays up until
        # the page's content actually changes; the next engine tick must not
        # paint the unchanged page straight back over it.
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        self._tick(service, ticks=3)
        assert service.vb_client.render.call_count == 1
        assert self._shown(service) == "GOOD MORNING"

    def test_page_returns_when_its_content_changes(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        self._tick(service, ticks=2)
        assert service.vb_client.render.call_count == 1
        result = Mock(available=True, formatted="WEATHER\nRAIN")
        self._tick(service, exiting=False, preview=lambda *_a, **_k: result)
        assert "RAIN" in self._shown(service)

    def test_exit_delivery_wraps_text(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING EVERYONE HAVE A GREAT DAY TODAY", board_id="b1"))
        self._tick(service, device_type="flagship")
        assert self._shown(service).split("\n") == ["GOOD MORNING EVERYONE", "HAVE A GREAT DAY TODAY"]
        rt = service._ensure_primary_runtime()
        assert rt.silence_queued_shown == rt.last_active_page_content
        # The next tick keeps it (the adoption block matched the exact string).
        self._tick(service, device_type="flagship", exiting=False)
        assert service.vb_client.render.call_count == 1

    def test_lines_intent_is_laid_out_as_given(self, service):
        silence_queue.hold(HeldSend.lines(["GOOD", "MORNING"], board_id="b1"))
        self._tick(service, device_type="flagship")
        assert self._shown(service).split("\n") == ["GOOD", "MORNING"]

    def test_page_intent_is_rendered_fresh_at_exit(self, service):
        silence_queue.hold(HeldSend.page("transit", board_id="b1"))
        transit = Mock(available=True, formatted="TRAIN IN 4 MIN")
        weather = Mock(available=True, formatted="WEATHER\nTEMP")
        calls = []

        def preview(page_id, force_refresh=False, **_kwargs):
            calls.append((page_id, force_refresh))
            return transit if page_id == "transit" else weather

        self._tick(service, device_type="flagship", preview=preview)
        assert ("transit", True) in calls
        assert self._shown(service) == "TRAIN IN 4 MIN"
        assert silence_queue.peek("b1") is None

    def test_a_deleted_page_intent_is_discarded_with_a_warning(self, service, caplog):
        silence_queue.hold(HeldSend.page("gone", board_id="b1"))
        weather = Mock(available=True, formatted="WEATHER\nTEMP")
        with caplog.at_level(logging.WARNING, logger="src.main"):
            self._tick(service, preview=lambda pid, **_k: None if pid == "gone" else weather)
            self._tick(service, exiting=False, preview=lambda pid, **_k: None if pid == "gone" else weather)
        assert silence_queue.peek("b1") is None
        assert any("can no longer be rendered" in r.getMessage() for r in caplog.records)
        assert "WEATHER" in self._shown(service)

    def test_display_intent_is_fetched_fresh_at_exit(self, service):
        silence_queue.hold(HeldSend.display("weather", board_id="b1"))
        display_service = Mock()
        display_service.get_display.return_value = Mock(available=True, formatted="SUNNY 72")
        with patch("src.displays.service.get_display_service", return_value=display_service):
            self._tick(service, device_type="flagship")
        display_service.get_display.assert_called_once_with("weather")
        assert self._shown(service) == "SUNNY 72"

    @pytest.mark.parametrize("why", ["paused", "ui_only"])
    def test_held_discarded_when_exiting_paused_or_ui_only(self, service, why, caplog):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        with caplog.at_level(logging.INFO, logger="src.main"):
            self._tick(service, paused=why == "paused", ui_only=why == "ui_only")
        assert silence_queue.peek("b1") is None
        assert any("Discarding message held during silence" in r.getMessage() for r in caplog.records)
        # A later window with no sends paints nothing held.
        self._tick(service)
        for call in service.vb_client.render.call_args_list:
            assert "GOOD MORNING" not in _decode_board_text(call.args[0])

    def test_failed_delivery_keeps_entry_and_retries(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        service.vb_client.render.return_value = (False, False)
        self._tick(service)
        assert silence_queue.peek("b1") is not None
        service.vb_client.render.return_value = (True, True)
        self._tick(service, exiting=False)
        assert self._shown(service) == "GOOD MORNING"
        assert silence_queue.peek("b1") is None

    def test_failed_delivery_does_not_hold_back_the_page_once_the_option_is_off(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        service.vb_client.render.return_value = (False, False)
        self._tick(service)
        service.vb_client.render.return_value = (True, True)
        self._tick(service, enabled=False, exiting=False)
        assert "WEATHER" in self._shown(service)

    def test_held_send_survives_a_restart(self, service):
        silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
        silence_queue._reset_for_tests()  # what a process restart does to memory
        self._tick(service)
        assert self._shown(service) == "GOOD MORNING"


def test_override_write_supersedes_held(monkeypatch):
    """Hold 'NIGHT', then an override active-page send lands: exit paints the page."""
    from fastapi.testclient import TestClient

    from src.api_server import app
    from src.pages.models import PageCreate
    from src.pages.service import get_page_service
    from tests.live_boards import install_live_boards
    from tests.test_wire_goldens import install_wire_recorder, local_flagship

    wire = install_wire_recorder(monkeypatch)
    service = install_live_boards([local_flagship("b1")])
    page = get_page_service().create_page(PageCreate(name="Weather", type="template", template=["SUNNY"]))
    silence_queue.hold(HeldSend.text("NIGHT", board_id="b1"))
    with silenced(holds=True):
        resp = TestClient(app).put(
            "/settings/active-page", json={"page_id": page.id, "board_id": "b1", "override_silence": True}
        )
    assert resp.json()["sent_to_board"] is True
    assert silence_queue.peek("b1") is None
    wire.take()
    rt = service.runtimes["b1"]
    rt.last_silence_mode_active = True
    rt.last_active_page_content = None
    service.check_and_send_active_page()
    for call in wire.take():
        assert "NIGHT" not in json.dumps(call)
