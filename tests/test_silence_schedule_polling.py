"""Tests for silence-mode behavior in DisplayService.check_and_send_active_page.

Bug fix: the polling loop kept re-sending updates and refreshing plugin data
during the silence window. The previous logic detected "indicator on board"
by searching for the literal word "snoozing" in the cached *content text*,
but the SNOOZING indicator is only stamped onto the board *array* — it is
never part of the content text. As a result every poll re-entered the
"allow update" branch, woke the board, and called plugin APIs.

These tests validate that:
- During steady silence, plugin rendering is NOT called and the board is NOT sent to.
- Triggers are suppressed during silence.
- A single send happens when entering silence (with the SNOOZING indicator).
- Exiting silence forces a normal update through (instead of being skipped
  by the "content unchanged" cache).
"""

from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def service_factory():
    """Build a DisplayService with mocked services. The caller controls the
    return value of Config.is_silence_mode_active per test."""

    def _make(is_silence: bool):
        patches = {
            'config': patch('src.main.Config'),
            'settings': patch('src.main.get_settings_service'),
            'page': patch('src.main.get_page_service'),
            'schedule': patch('src.main.get_schedule_service'),
            'carousel': patch('src.main.get_carousel_service'),
            'trigger': patch('src.main.get_trigger_service'),
        }
        mocks = {name: p.start() for name, p in patches.items()}

        mocks['config'].is_silence_mode_active.return_value = is_silence
        mocks['config'].get_transition_settings.return_value = {"strategy": None}

        settings_service = Mock()
        settings_service.is_schedule_enabled.return_value = False
        settings_service.get_active_page_id.return_value = "page-1"
        settings_service.get_polling_interval.return_value = 60
        board_settings = Mock()
        board_settings.boards = []
        settings_service.get_board_settings.return_value = board_settings
        transition = Mock()
        transition.strategy = None
        transition.step_interval_ms = 0
        transition.step_size = 1
        settings_service.get_transition_settings.return_value = transition
        mocks['settings'].return_value = settings_service

        page_service = Mock()
        mock_page = Mock()
        mock_page.id = "page-1"
        mock_page.device_type = "flagship"
        mock_page.transition_strategy = None
        mock_page.transition_interval_ms = None
        mock_page.transition_step_size = None
        page_service.get_page.return_value = mock_page
        preview = Mock()
        preview.available = True
        preview.formatted = "Hello World"
        page_service.preview_page.return_value = preview
        mocks['page'].return_value = page_service

        from src.main import DisplayService
        svc = DisplayService()
        svc.vb_client = Mock()
        svc.vb_client.send_characters.return_value = (True, True)

        return svc, mocks, page_service, patches

    started = []

    def factory(is_silence: bool):
        svc, mocks, page_service, patches = _make(is_silence)
        started.append(patches)
        return svc, mocks, page_service

    yield factory

    for patches in started:
        for p in patches.values():
            p.stop()


class TestSilenceModeShortCircuit:
    """Once SNOOZING has been displayed, the polling loop must not touch the
    board or plugin APIs again until silence ends."""

    def test_steady_silence_skips_render_and_send(self, service_factory):
        svc, mocks, page_service = service_factory(is_silence=True)

        # Simulate prior tick: we are already in silence and the SNOOZING
        # indicator has been pushed to the board.
        svc._last_silence_mode_active = True
        svc._snoozing_message_sent = True
        svc._last_active_page_id = "page-1"
        svc._last_active_page_content = "Hello World"

        result = svc.check_and_send_active_page()

        assert result is False
        # CRITICAL: plugin rendering must NOT happen during steady silence.
        page_service.preview_page.assert_not_called()
        # Board must not be touched.
        svc.vb_client.send_characters.assert_not_called()

    def test_steady_silence_does_not_evaluate_triggers(self, service_factory):
        """Trigger plugins must not be polled during silence."""
        svc, mocks, page_service = service_factory(is_silence=True)
        svc._last_silence_mode_active = True
        svc._snoozing_message_sent = True

        with patch.object(svc, '_check_trigger_override') as trig:
            svc.check_and_send_active_page()
            trig.assert_not_called()


class TestEnteringSilence:
    """When silence becomes active, send exactly one update with the
    SNOOZING indicator stamped on the board."""

    def test_entering_silence_sends_once_with_indicator(self, service_factory):
        svc, mocks, page_service = service_factory(is_silence=True)

        # Prior tick: not silenced.
        svc._last_silence_mode_active = False
        svc._snoozing_message_sent = False

        with patch.object(svc, '_check_trigger_override', return_value=None):
            result = svc.check_and_send_active_page()

        assert result is True
        svc.vb_client.send_characters.assert_called_once()
        assert svc._snoozing_message_sent is True
        assert svc._last_silence_mode_active is True

        # Verify SNOOZING was stamped on the board array (bottom-right).
        sent_array = svc.vb_client.send_characters.call_args.args[0]
        last_row_text = "".join(
            chr(c + 64) if 1 <= c <= 26 else "?" for c in sent_array[-1]
        )
        assert "SNOOZING" in last_row_text

    def test_second_tick_after_entering_silence_is_a_noop(self, service_factory):
        """After the entering-silence send, subsequent polls must not send."""
        svc, mocks, page_service = service_factory(is_silence=True)
        svc._last_silence_mode_active = False
        svc._snoozing_message_sent = False

        with patch.object(svc, '_check_trigger_override', return_value=None):
            svc.check_and_send_active_page()
        page_service.preview_page.reset_mock()
        svc.vb_client.send_characters.reset_mock()

        # Next tick — still silenced.
        svc.check_and_send_active_page()

        page_service.preview_page.assert_not_called()
        svc.vb_client.send_characters.assert_not_called()


class TestExitingSilence:
    """When silence ends, the next update must go through even if the
    rendered content matches the cached content (the board still shows the
    SNOOZING indicator and needs to be repainted)."""

    def test_exiting_silence_forces_resend_even_if_content_unchanged(
        self, service_factory
    ):
        svc, mocks, page_service = service_factory(is_silence=False)

        # Prior tick: in silence, indicator was on the board, content cached.
        svc._last_silence_mode_active = True
        svc._snoozing_message_sent = True
        svc._last_active_page_id = "page-1"
        svc._last_active_page_content = "Hello World"  # same as preview.formatted

        with patch.object(svc, '_check_trigger_override', return_value=None):
            result = svc.check_and_send_active_page()

        # MUST re-send to clear the SNOOZING indicator.
        assert result is True
        svc.vb_client.send_characters.assert_called_once()
        assert svc._snoozing_message_sent is False
        assert svc._last_silence_mode_active is False

        # Indicator should NOT be present on the freshly-sent board.
        sent_array = svc.vb_client.send_characters.call_args.args[0]
        last_row_text = "".join(
            chr(c + 64) if 1 <= c <= 26 else "?" for c in sent_array[-1]
        )
        assert "SNOOZING" not in last_row_text
