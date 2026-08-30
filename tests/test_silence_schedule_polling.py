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
            "config": patch("src.main.Config"),
            "settings": patch("src.main.get_settings_service"),
            "page": patch("src.main.get_page_service"),
            "schedule": patch("src.main.get_schedule_service"),
            "collection": patch("src.main.get_collection_service"),
            "trigger": patch("src.main.get_trigger_service"),
        }
        mocks = {name: p.start() for name, p in patches.items()}

        mocks["config"].is_silence_mode_active.return_value = is_silence
        mocks["config"].get_transition_settings.return_value = {"strategy": None}
        mocks["config"].SILENCE_SCHEDULE_MODE = "indicator"
        mocks["config"].SILENCE_SCHEDULE_INDICATOR_TEXT = "SNOOZING"
        mocks["config"].SILENCE_SCHEDULE_INDICATOR_POSITION = "center"
        mocks["config"].SILENCE_SCHEDULE_PAGE_ID = None
        # Since issue #1788 the engine resolves a board's silence settings via
        # Config.silence_config_for(board_id); the classproperties above are
        # only the install-wide mirror.
        mocks["config"].silence_config_for.return_value = {
            "enabled": True,
            "start_time": "04:00+00:00",
            "end_time": "15:00+00:00",
            "mode": "indicator",
            "page_id": None,
            "indicator_text": "SNOOZING",
            "indicator_position": "center",
        }

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
        mocks["settings"].return_value = settings_service

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
        mocks["page"].return_value = page_service

        from src.main import DisplayService

        svc = DisplayService()
        svc.vb_client = Mock()
        svc.vb_client.send_characters.return_value = (True, True)
        svc.vb_client.render.return_value = (True, True)

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
        svc, _mocks, page_service = service_factory(is_silence=True)

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
        svc.vb_client.render.assert_not_called()

    def test_steady_silence_does_not_evaluate_triggers(self, service_factory):
        """Trigger plugins must not be polled during silence."""
        svc, _mocks, _page_service = service_factory(is_silence=True)
        svc._last_silence_mode_active = True
        svc._snoozing_message_sent = True

        with patch.object(svc, "_check_trigger_override") as trig:
            svc.check_and_send_active_page()
            trig.assert_not_called()


class TestEnteringSilence:
    """When silence becomes active, send exactly one update with the
    SNOOZING indicator stamped on the board."""

    def test_entering_silence_sends_once_with_indicator(self, service_factory):
        svc, _mocks, _page_service = service_factory(is_silence=True)

        # Prior tick: not silenced.
        svc._last_silence_mode_active = False
        svc._snoozing_message_sent = False

        with patch.object(svc, "_check_trigger_override", return_value=None):
            result = svc.check_and_send_active_page()

        assert result is True
        svc.vb_client.render.assert_called_once()
        assert svc._snoozing_message_sent is True
        assert svc._last_silence_mode_active is True

        # Verify SNOOZING was stamped on the board array (center row by default).
        sent_array = svc.vb_client.render.call_args.args[0]
        center_row = sent_array[len(sent_array) // 2]
        center_row_text = "".join(chr(c + 64) if 1 <= c <= 26 else "?" for c in center_row)
        assert "SNOOZING" in center_row_text

    def test_second_tick_after_entering_silence_is_a_noop(self, service_factory):
        """After the entering-silence send, subsequent polls must not send."""
        svc, _mocks, page_service = service_factory(is_silence=True)
        svc._last_silence_mode_active = False
        svc._snoozing_message_sent = False

        with patch.object(svc, "_check_trigger_override", return_value=None):
            svc.check_and_send_active_page()
        page_service.preview_page.reset_mock()
        svc.vb_client.render.reset_mock()

        # Next tick — still silenced.
        svc.check_and_send_active_page()

        page_service.preview_page.assert_not_called()
        svc.vb_client.render.assert_not_called()


class TestExitingSilence:
    """When silence ends, the next update must go through even if the
    rendered content matches the cached content (the board still shows the
    SNOOZING indicator and needs to be repainted)."""

    def test_exiting_silence_forces_resend_even_if_content_unchanged(self, service_factory):
        svc, _mocks, _page_service = service_factory(is_silence=False)

        # Prior tick: in silence, indicator was on the board, content cached.
        svc._last_silence_mode_active = True
        svc._snoozing_message_sent = True
        svc._last_active_page_id = "page-1"
        svc._last_active_page_content = "Hello World"  # same as preview.formatted

        with patch.object(svc, "_check_trigger_override", return_value=None):
            result = svc.check_and_send_active_page()

        # MUST re-send to clear the SNOOZING indicator.
        assert result is True
        svc.vb_client.render.assert_called_once()
        assert svc._snoozing_message_sent is False
        assert svc._last_silence_mode_active is False

        # Indicator should NOT be present on the freshly-sent board.
        sent_array = svc.vb_client.render.call_args.args[0]
        last_row_text = "".join(chr(c + 64) if 1 <= c <= 26 else "?" for c in sent_array[-1])
        assert "SNOOZING" not in last_row_text


def _sleep_that_stops_after(svc, iterations, on_iteration=None):
    """Fake ``time.sleep`` that drives the run loop for a fixed number of ticks.

    Replaces the wall clock entirely: each call is one simulated second, so a
    silence window can be walked tick by tick without any real waiting.
    """
    state = {"ticks": 0}

    def _fake_sleep(_seconds):
        state["ticks"] += 1
        if on_iteration is not None:
            on_iteration(state["ticks"])
        if state["ticks"] >= iterations:
            svc.running = False

    return _fake_sleep


class TestSilenceBoundaryDetector:
    """The 1 Hz boundary detector must fire once per boundary, not once per
    second, even when the board's update path returns early (issue #1740)."""

    def test_paused_board_does_not_force_an_update_every_second_during_silence(self, service_factory):
        svc, mocks, _page_service = service_factory(is_silence=True)
        mocks["settings"].return_value.is_paused.return_value = True

        with (
            patch.object(svc, "check_and_send_active_page", wraps=svc.check_and_send_active_page) as drive,
            patch("src.main.schedule"),
            patch("src.main.time.sleep", _sleep_that_stops_after(svc, 5)),
        ):
            svc.run()

        # Only the initial update before the loop; the detector must stay quiet.
        assert drive.call_count == 1

    def test_render_failure_does_not_force_an_update_every_second_during_silence(self, service_factory):
        svc, mocks, page_service = service_factory(is_silence=True)
        failed_preview = Mock()
        failed_preview.available = False
        page_service.preview_page.return_value = failed_preview
        mocks["settings"].return_value.is_paused.return_value = False

        with (
            patch.object(svc, "check_and_send_active_page", wraps=svc.check_and_send_active_page) as drive,
            patch.object(svc, "_check_trigger_override", return_value=None),
            patch("src.main.schedule"),
            patch("src.main.time.sleep", _sleep_that_stops_after(svc, 5)),
        ):
            svc.run()

        assert drive.call_count == 1

    def test_crossing_into_silence_forces_exactly_one_update(self, service_factory):
        svc, mocks, _page_service = service_factory(is_silence=False)
        mocks["settings"].return_value.is_paused.return_value = True

        silence = {"active": False}
        mocks["config"].is_silence_mode_active.side_effect = lambda: silence["active"]

        def _flip_at_tick_3(tick):
            if tick == 3:
                silence["active"] = True

        with (
            patch.object(svc, "check_and_send_active_page", wraps=svc.check_and_send_active_page) as drive,
            patch("src.main.schedule"),
            patch("src.main.time.sleep", _sleep_that_stops_after(svc, 6, _flip_at_tick_3)),
        ):
            svc.run()

        # One initial update + exactly one forced update at the boundary.
        assert drive.call_count == 2

    def test_clientless_primary_does_not_force_an_update_every_second_during_silence(self, service_factory):
        """A primary board with a runtime but no client is a normal running
        state since #1749/#1813 — the fleet keeps going while that one board is
        skipped. Its silence flag must still be latched, or the 1 Hz boundary
        detector sees a permanent mismatch and re-drives every board once per
        second for the whole silence window (issue #1740).
        """
        svc, mocks, page_service = service_factory(is_silence=True)
        svc.vb_client = None
        assert svc._ensure_primary_runtime().client is None
        mocks["settings"].return_value.is_paused.return_value = False

        with (
            # The fleet came up; only the primary lacks a client (issue #1749).
            patch.object(svc, "initialize", return_value=True),
            patch.object(svc, "check_and_send_active_page", wraps=svc.check_and_send_active_page) as drive,
            patch.object(svc, "_check_trigger_override", return_value=None),
            patch("src.main.schedule"),
            patch("src.main.time.sleep", _sleep_that_stops_after(svc, 5)),
        ):
            svc.run()

        # Only the initial update before the loop — not one per simulated second.
        assert drive.call_count == 1
        assert page_service.preview_page.call_count == 1
