"""The display engine sends a page's canvas layers and dedupes on them (design §3 step 3)."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from src.canvas import CanvasLayer
from src.displays.service import DisplayResult
from src.led.charsets import BUILTIN_CHARACTER_SETS
from src.main import DisplayService

RED = CanvasLayer(x=0, y=0, w=1, h=1, rgba=bytes([255, 0, 0, 255]))
BLUE = CanvasLayer(x=0, y=0, w=1, h=1, rgba=bytes([0, 0, 255, 255]))


@pytest.fixture
def service():
    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.character_set = BUILTIN_CHARACTER_SETS["led_3x5"]  # a rich (LED) output
    svc.vb_client.render.return_value = (True, True)
    svc.vb_client.last_send_throttled = False
    svc.vb_client.last_send_preempted = False
    settings = Mock()
    settings.is_schedule_enabled.return_value = False
    settings.get_primary_board_id.return_value = None
    settings.get_temporary_override.return_value = None
    settings.consume_temporary_override.return_value = None
    settings.get_active_page_id.return_value = "p"
    settings.get_board_settings.return_value = Mock(boards=[{"device_type": "note"}])
    settings.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)
    svc._test_settings = settings
    return svc


def _tick(service, layers):
    page = Mock(
        id="p", device_type="note", transition_strategy=None, transition_interval_ms=None, transition_step_size=None
    )
    page_service = Mock()
    page_service.get_page.return_value = page
    page_service.preview_page.return_value = DisplayResult("page:template", "HELLO", {}, True, layers=list(layers))
    settings = service._test_settings
    config = Mock()
    config.is_silence_mode_active.return_value = False
    with (
        patch("src.main.get_page_service", return_value=page_service),
        patch("src.main.get_settings_service", return_value=settings),
        patch("src.main.get_schedule_service"),
        patch("src.main.Config", config),
        patch.object(service, "_check_trigger_override", return_value=None),
    ):
        return service.check_and_send_active_page()


def test_the_rich_frame_sent_carries_the_layers(service):
    assert _tick(service, [RED]) is True
    cells = service.vb_client.render.call_args.kwargs["cells"]
    assert cells.layers == (RED,)


def test_a_canvas_change_alone_is_sent_and_an_unchanged_one_is_not(service):
    _tick(service, [RED])
    _tick(service, [BLUE])
    assert service.vb_client.render.call_count == 2
    assert service.vb_client.render.call_args.kwargs["cells"].layers == (BLUE,)
    _tick(service, [BLUE])
    assert service.vb_client.render.call_count == 2


def test_a_page_without_layers_dedupes_on_its_text_as_before(service):
    _tick(service, [])
    assert service._last_active_page_content == "HELLO"
    _tick(service, [])
    assert service.vb_client.render.call_count == 1
