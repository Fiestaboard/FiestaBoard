"""Issue #1944: optionally show the last send blocked during silence when it ends."""

from unittest.mock import patch

import pytest

from src import silence_queue
from src.config import resolve_silence_schedule
from tests.test_silence_mode_display import TestSilenceModeDispatch, _decode_board_text


@pytest.fixture(autouse=True)
def _clean_queue():
    silence_queue.clear()
    yield
    silence_queue.clear()


def test_queue_keeps_only_latest_message_per_board():
    silence_queue.queue_message("b1", "FIRST")
    silence_queue.queue_message("b1", "SECOND")
    assert silence_queue.pop_message("b1") == "SECOND"
    assert silence_queue.pop_message("b1") is None


def test_show_queued_on_exit_defaults_off():
    assert resolve_silence_schedule({"enabled": True})["show_queued_on_exit"] is False


def test_show_queued_on_exit_resolves_per_board():
    feature = {"enabled": True, "by_board": {"b1": {"show_queued_on_exit": True}}}
    assert resolve_silence_schedule(feature, "b1")["show_queued_on_exit"] is True
    assert resolve_silence_schedule(feature, "b2")["show_queued_on_exit"] is False


class TestExitDelivery:
    def _exit_tick(self, service, *, enabled):
        service._last_silence_mode_active = True
        _, page_service, settings, config = TestSilenceModeDispatch()._patch_common(mode="freeze", silence_active=False)
        settings.get_primary_board_id.return_value = "b1"
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
            return service.check_and_send_active_page()

    def test_queued_message_is_shown_when_silence_ends(self, service):
        silence_queue.queue_message("b1", "GOOD MORNING")
        self._exit_tick(service, enabled=True)
        args, _ = service.vb_client.render.call_args
        assert _decode_board_text(args[0]).strip() == "GOOD MORNING"
        assert silence_queue.pop_message("b1") is None

    def test_queued_message_ignored_when_option_off(self, service):
        silence_queue.queue_message("b1", "GOOD MORNING")
        self._exit_tick(service, enabled=False)
        for call in service.vb_client.render.call_args_list:
            assert "GOOD MORNING" not in _decode_board_text(call.args[0])
