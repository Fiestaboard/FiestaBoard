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
            inst.get_board_settings.return_value = Mock(
                boards=[{"device_type": "note"}]
            )
            inst.get_transition_settings.return_value = Mock(
                strategy=None, step_interval_ms=500, step_size=1
            )
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
            inst.get_board_settings.return_value = Mock(
                boards=[{"device_type": "flagship"}]
            )
            inst.get_transition_settings.return_value = Mock(
                strategy=None, step_interval_ms=500, step_size=1
            )
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
        settings.is_schedule_enabled.return_value = False
        settings.get_active_page_id.return_value = "active-page"
        settings.get_board_settings.return_value = Mock(boards=[{"device_type": "note"}])
        settings.get_transition_settings.return_value = Mock(
            strategy=None, step_interval_ms=500, step_size=1
        )

        config = Mock()
        config.is_silence_mode_active.return_value = silence_active
        config.SILENCE_SCHEDULE_MODE = mode
        config.SILENCE_SCHEDULE_PAGE_ID = page_id

        return page, page_service, settings, config

    def test_freeze_mode_does_not_send(self, service):
        _, page_service, settings, config = self._patch_common(mode="freeze")
        with patch("src.main.get_page_service", return_value=page_service), \
             patch("src.main.get_settings_service", return_value=settings), \
             patch("src.main.get_schedule_service"), \
             patch("src.main.Config", config), \
             patch.object(service, "_check_trigger_override", return_value=None):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()
        assert service._last_silence_mode_active is True

    def test_freeze_mode_blocks_subsequent_ticks(self, service):
        service._last_silence_mode_active = True
        _, page_service, settings, config = self._patch_common(mode="freeze")
        with patch("src.main.get_page_service", return_value=page_service), \
             patch("src.main.get_settings_service", return_value=settings), \
             patch("src.main.get_schedule_service"), \
             patch("src.main.Config", config), \
             patch.object(service, "_check_trigger_override", return_value=None):
            sent = service.check_and_send_active_page()

        assert sent is False
        service.vb_client.send_characters.assert_not_called()

    def test_indicator_mode_sends_once(self, service):
        _, page_service, settings, config = self._patch_common(mode="indicator")
        with patch("src.main.get_page_service", return_value=page_service), \
             patch("src.main.get_settings_service", return_value=settings), \
             patch("src.main.get_schedule_service"), \
             patch("src.main.Config", config), \
             patch.object(service, "_check_trigger_override", return_value=None):
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
        active_page, page_service, settings, config = self._patch_common(
            mode="page", page_id="silence-page"
        )

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

        with patch("src.main.get_page_service", return_value=page_service), \
             patch("src.main.get_settings_service", return_value=settings), \
             patch("src.main.get_schedule_service"), \
             patch("src.main.Config", config), \
             patch.object(service, "_check_trigger_override", return_value=None):
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
        active_page, page_service, settings, config = self._patch_common(
            mode="page", page_id="missing-page"
        )

        def _get_page(pid):
            if pid == "missing-page":
                return None
            return active_page

        page_service.get_page.side_effect = _get_page

        with patch("src.main.get_page_service", return_value=page_service), \
             patch("src.main.get_settings_service", return_value=settings), \
             patch("src.main.get_schedule_service"), \
             patch("src.main.Config", config), \
             patch.object(service, "_check_trigger_override", return_value=None):
            sent = service.check_and_send_active_page()

        assert sent is True
        args, _ = service.vb_client.send_characters.call_args
        board_array = args[0]
        assert _decode_board_text(board_array).strip() == "SNOOZING"
