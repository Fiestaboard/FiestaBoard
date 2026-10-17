"""Issue #1944: optionally show the last send blocked during silence when it ends."""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from src import silence_queue
from src.board_api import routes as board_routes
from src.config import resolve_silence_schedule
from src.main import DisplayService
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


@pytest.mark.parametrize("enabled", [True, False])
def test_blocked_send_is_queued_only_when_enabled(enabled):
    config = Mock()
    config.silence_config_for.return_value = {"show_queued_on_exit": enabled}
    with (
        patch.object(board_routes, "_silence_active", return_value=True),
        patch("src.config.Config", config),
        pytest.raises(HTTPException) as exc,
    ):
        board_routes._raise_if_silenced("b1", "HELLO")
    assert exc.value.status_code == 409
    assert silence_queue.pop_message("b1") == ("HELLO" if enabled else None)


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
        _, page_service, settings, config = _Dispatch()._patch_common(mode="freeze", silence_active=False)
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
