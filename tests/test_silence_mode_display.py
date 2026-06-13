"""Tests for silence-mode behaviour in DisplayService.

Covers the three silence modes introduced for the "Silence Schedule -
Display on Note" issue:

- ``indicator`` (default): clear the board and show "SNOOZING" centered,
  sized to the device. Must not overlay existing content.
- ``freeze``: never send to the board while silence is active.
- ``page``: render a configured page once and freeze it on the board.
"""

from unittest.mock import Mock, patch

import pytest

from src.board_chars import BoardChars
from src.main import DisplayService


@pytest.fixture
def service():
    svc = DisplayService()
    svc.vb_client = Mock()
    svc.vb_client.send_characters.return_value = (True, True)
    return svc


def _decode_board_text(board_array):
    """Turn a board character array back into a flat string for assertions."""
    # Build a reverse map from BoardChars constants. We only need letters,
    # digits, space and a few punctuation chars for our assertions.
    rev = {0: " "}
    for i, ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ", start=1):
        rev[i] = ch
    for i, ch in enumerate("123456789", start=27):
        rev[i] = ch
    rev[36] = "0"
    rev[50] = ":"
    rev[55] = ","
    rev[56] = "."

    out = []
    for row in board_array:
        line = "".join(rev.get(code, "?") for code in row)
        out.append(line.rstrip())
    return "\n".join(line for line in out if line)


class TestSilenceIndicator:
    """The indicator mode must produce a clean SNOOZING-only board."""

    def test_note_indicator_fits_and_does_not_overlay(self, service):
        with patch("src.main.get_settings_service") as settings_svc:
            inst = Mock()
            inst.get_board_settings.return_value = Mock(boards=[{"device_type": "note"}])
            inst.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)
            settings_svc.return_value = inst

            sent = service._send_silence_indicator("note")

        assert sent is True
        # Captured board array - must be 3x15 (Note dims) and contain only
        # SNOOZING (no other characters).
        args, _ = service.vb_client.send_characters.call_args
        board_array = args[0]
        assert len(board_array) == 3
        assert all(len(row) == 15 for row in board_array)

        text = _decode_board_text(board_array)
        assert text.strip() == "SNOOZING"

        # Internal state markers consistent with "silenced".
        assert service._last_silence_mode_active is True
        assert service._snoozing_message_sent is True

    def test_flagship_indicator_fits(self, service):
        with patch("src.main.get_settings_service") as settings_svc:
            inst = Mock()
            inst.get_board_settings.return_value = Mock(boards=[{"device_type": "flagship"}])
            inst.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)
            settings_svc.return_value = inst

            assert service._send_silence_indicator("flagship") is True

        args, _ = service.vb_client.send_characters.call_args
        board_array = args[0]
        assert len(board_array) == 6
        assert all(len(row) == 22 for row in board_array)
        assert _decode_board_text(board_array).strip() == "SNOOZING"


class TestSilenceModeDispatch:
    """check_and_send_active_page must dispatch to the right silence helper."""

    def _patch_common(self, mode="indicator", page_id=None, silence_active=True):
        """Common patches for the dispatch test."""
        page = Mock(
            id="active-page",
            device_type="note",
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )
        result = Mock(available=True, formatted="WEATHER\nTEMP")

        page_service = Mock()
        page_service.get_page.return_value = page
        page_service.preview_page.return_value = result

        settings = Mock()
        # Silence-mode dispatch is a sub-feature of the polling loop, so these
        # tests assume schedule mode is on — the schedule-off guard (#970)
        # would otherwise short-circuit before silence runs.
        settings.is_schedule_enabled.return_value = True
        settings.get_active_page_id.return_value = "active-page"
        settings.consume_temporary_override.return_value = None
        settings.get_board_settings.return_value = Mock(boards=[{"device_type": "note"}])
        settings.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)

        config = Mock()
        config.is_silence_mode_active.return_value = silence_active
        config.SILENCE_SCHEDULE_MODE = mode
        config.SILENCE_SCHEDULE_PAGE_ID = page_id
        config.SILENCE_SCHEDULE_INDICATOR_TEXT = "SNOOZING"
        config.SILENCE_SCHEDULE_INDICATOR_POSITION = "center"

        return page, page_service, settings, config

    def test_freeze_mode_does_not_send(self, service):
        _, page_service, settings, config = self._patch_common(mode="freeze")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()
        assert service._last_silence_mode_active is True

    def test_freeze_mode_blocks_subsequent_ticks(self, service):
        service._last_silence_mode_active = True
        _, page_service, settings, config = self._patch_common(mode="freeze")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()

    def test_indicator_mode_sends_once(self, service):
        _, page_service, settings, config = self._patch_common(mode="indicator")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            # First tick: enters silence, sends indicator
            service.check_and_send_active_page()
            assert service.vb_client.send_characters.call_count == 1

            # The board should display ONLY SNOOZING - not the page content
            args, _ = service.vb_client.send_characters.call_args
            board_array = args[0]
            assert _decode_board_text(board_array).strip() == "SNOOZING"

            # Second tick: still silenced, must NOT send again
            service.check_and_send_active_page()
            assert service.vb_client.send_characters.call_count == 1

    def test_page_mode_renders_configured_page(self, service):
        active_page, page_service, settings, config = self._patch_common(mode="page", page_id="silence-page")

        # Configure get_page to return the silence page when asked.
        silence_page = Mock(
            id="silence-page",
            device_type="note",
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )
        silence_result = Mock(available=True, formatted="GOOD NIGHT")

        def _get_page(pid):
            if pid == "silence-page":
                return silence_page
            return active_page

        def _preview(pid, force_refresh=False):
            if pid == "silence-page":
                return silence_result
            return Mock(available=True, formatted="WEATHER\nTEMP")

        page_service.get_page.side_effect = _get_page
        page_service.preview_page.side_effect = _preview

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()
            assert sent is True
            # The board content should be the silence page, not the active page.
            args, _ = service.vb_client.send_characters.call_args
            board_array = args[0]
            assert "GOOD NIGHT" in _decode_board_text(board_array)
            # And further ticks must not send again.
            service.check_and_send_active_page()
            assert service.vb_client.send_characters.call_count == 1

    def test_page_mode_falls_back_to_indicator_when_page_missing(self, service):
        active_page, page_service, settings, config = self._patch_common(mode="page", page_id="missing-page")

        def _get_page(pid):
            if pid == "missing-page":
                return None
            return active_page

        page_service.get_page.side_effect = _get_page

        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is True
        args, _ = service.vb_client.send_characters.call_args
        board_array = args[0]
        assert _decode_board_text(board_array).strip() == "SNOOZING"


class TestCustomIndicatorTextAndPosition:
    """Indicator dispatch must honor custom text + position from Config."""

    def _patch_common(self, indicator_text="SNOOZING", indicator_position="center"):
        page = Mock(
            id="active-page",
            device_type="flagship",
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )
        result = Mock(available=True, formatted="WEATHER\nTEMP")

        page_service = Mock()
        page_service.get_page.return_value = page
        page_service.preview_page.return_value = result

        settings = Mock()
        # Schedule mode on — see comment in TestSilenceModeDispatch._patch_common.
        settings.is_schedule_enabled.return_value = True
        settings.get_active_page_id.return_value = "active-page"
        settings.consume_temporary_override.return_value = None
        settings.get_board_settings.return_value = Mock(boards=[{"device_type": "flagship"}])
        settings.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)

        config = Mock()
        config.is_silence_mode_active.return_value = True
        config.SILENCE_SCHEDULE_MODE = "indicator"
        config.SILENCE_SCHEDULE_PAGE_ID = None
        config.SILENCE_SCHEDULE_INDICATOR_TEXT = indicator_text
        config.SILENCE_SCHEDULE_INDICATOR_POSITION = indicator_position
        return page_service, settings, config

    def test_indicator_uses_custom_text(self, service):
        page_service, settings, config = self._patch_common(indicator_text="ZZZ")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            service.check_and_send_active_page()

        args, _ = service.vb_client.send_characters.call_args
        board_array = args[0]
        text = _decode_board_text(board_array).strip()
        assert text == "ZZZ"

    def test_indicator_at_bottom_right_for_flagship(self, service):
        page_service, settings, config = self._patch_common(indicator_text="ZZZ", indicator_position="bottom-right")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            service.check_and_send_active_page()

        args, _ = service.vb_client.send_characters.call_args
        board_array = args[0]
        # Flagship: 6 rows x 22 cols. Bottom row, right-aligned ZZZ at cols 19-21.
        assert len(board_array) == 6
        bottom = board_array[5]
        # All cols except 19,20,21 should be SPACE
        for col, code in enumerate(bottom):
            if col in (19, 20, 21):
                assert code != BoardChars.SPACE
            else:
                assert code == BoardChars.SPACE
        # Top 5 rows entirely blank
        for row in board_array[:5]:
            assert all(c == BoardChars.SPACE for c in row)

    def test_freeze_is_default_when_mode_unset(self, service):
        """If config provides no mode (so Config.SILENCE_SCHEDULE_MODE == 'freeze'), no send."""
        page_service, settings, config = self._patch_common()
        config.SILENCE_SCHEDULE_MODE = "freeze"
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()


class TestTemporaryOverrideDuringSilence:
    """A user-initiated temporary override must win over the silence schedule.

    Regression for issue #949 ("Override Quiet Hours"): when a user
    explicitly says "show this page right now for N minutes" we honor that
    intent even if the silence window is currently active. The plugin-based
    trigger path is unchanged (still suppressed by silence — see
    ``test_trigger_render_path.py``); only the explicit user override
    bypasses silence.
    """

    def _patch_common(self, has_override=True, silence_active=True, silence_mode="indicator"):
        from src.settings.service import TemporaryOverride

        # Active page that the schedule would otherwise show.
        active_page = Mock(
            id="active-page",
            device_type="note",
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )
        active_result = Mock(available=True, formatted="WEATHER\nTEMP")

        # The override page — what the user explicitly wants to see now.
        override_page = Mock(
            id="override-page",
            device_type="note",
            transition_strategy=None,
            transition_interval_ms=None,
            transition_step_size=None,
        )
        override_result = Mock(available=True, formatted="HELLO")

        def _get_page(pid):
            return override_page if pid == "override-page" else active_page

        def _preview(pid, force_refresh=False):
            return override_result if pid == "override-page" else active_result

        page_service = Mock()
        page_service.get_page.side_effect = _get_page
        page_service.preview_page.side_effect = _preview

        override = (
            TemporaryOverride(
                page_id="override-page",
                expires_at="2099-01-01T00:00:00+00:00",
                revert_mode="schedule",
            )
            if has_override
            else None
        )

        settings = Mock()
        # Schedule mode on — see comment in TestSilenceModeDispatch._patch_common.
        settings.is_schedule_enabled.return_value = True
        settings.get_active_page_id.return_value = "active-page"
        settings.get_board_settings.return_value = Mock(boards=[{"device_type": "note"}])
        settings.get_transition_settings.return_value = Mock(strategy=None, step_interval_ms=500, step_size=1)
        settings.consume_temporary_override.return_value = override

        config = Mock()
        config.is_silence_mode_active.return_value = silence_active
        config.SILENCE_SCHEDULE_MODE = silence_mode
        config.SILENCE_SCHEDULE_PAGE_ID = None
        config.SILENCE_SCHEDULE_INDICATOR_TEXT = "SNOOZING"
        config.SILENCE_SCHEDULE_INDICATOR_POSITION = "center"

        return page_service, settings, config

    def test_active_override_bypasses_silence_indicator(self, service):
        """With silence active and a fresh override, board shows the override page, not SNOOZING."""
        page_service, settings, config = self._patch_common(silence_mode="indicator")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is True
        args, _ = service.vb_client.send_characters.call_args
        text = _decode_board_text(args[0]).strip()
        assert "HELLO" in text
        assert "SNOOZING" not in text

    def test_active_override_bypasses_silence_freeze(self, service):
        """Freeze mode must NOT block an explicit user override."""
        page_service, settings, config = self._patch_common(silence_mode="freeze")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            sent = service.check_and_send_active_page()

        assert sent is True
        service.vb_client.send_characters.assert_called_once()
        args, _ = service.vb_client.send_characters.call_args
        assert "HELLO" in _decode_board_text(args[0])

    def test_no_override_still_silences(self, service):
        """Sanity: without an override, silence still produces the indicator."""
        page_service, settings, config = self._patch_common(has_override=False, silence_mode="indicator")
        with (
            patch("src.main.get_page_service", return_value=page_service),
            patch("src.main.get_settings_service", return_value=settings),
            patch(
                "src.main.get_schedule_service", return_value=Mock(get_active_page_id=Mock(return_value="active-page"))
            ),
            patch("src.main.Config", config),
            patch.object(service, "_check_trigger_override", return_value=None),
        ):
            service.check_and_send_active_page()

        args, _ = service.vb_client.send_characters.call_args
        assert _decode_board_text(args[0]).strip() == "SNOOZING"


class TestSendTriggerContent:
    """Tests for _send_trigger_content."""

    def test_device_type_passed_to_get_dimensions(self, service):
        """Regression #748: get_dimensions must receive device_type, not be called bare."""
        with (
            patch("src.main.get_settings_service") as mock_settings_svc,
            patch("src.main.get_dimensions") as mock_get_dims,
            patch.object(service, "_silence_device_type", return_value="note"),
        ):
            mock_settings_svc.return_value.get_transition_settings.return_value = Mock(
                strategy=None, step_interval_ms=500, step_size=1
            )
            mock_get_dims.return_value = Mock(rows=3, cols=15)

            service._send_trigger_content("HELLO")

        mock_get_dims.assert_called_once_with("note")

    def test_returns_false_when_no_client(self):
        svc = DisplayService()
        svc.vb_client = None
        assert svc._send_trigger_content("HELLO") is False

    def test_returns_false_when_content_unchanged(self, service):
        service._last_active_page_content = "SAME"
        assert service._send_trigger_content("SAME") is False
        service.vb_client.send_characters.assert_not_called()
