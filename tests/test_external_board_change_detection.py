"""Tests for external-board-change detection in the state poll (issue #1946).

The board-state poll already reads the primary board every cycle. When a
fresh read differs from what FiestaBoard itself last wrote, someone else
wrote the board (Vestaboard app, direct API call), so the board is no
longer showing the configured page. The poll must mark the runtime
out-of-band so MQTT/Home Assistant stops reporting the stale page —
mirroring what the web UI already shows from the same cache.

Clearing the flag stays with the engine's own page sends: a read that
matches ``_last_characters`` only proves the board shows whatever we
last wrote (which may itself be an out-of-band manual message), so the
poll never clears the flag.
"""

from unittest.mock import Mock

from src.main import DisplayService

SENT = [[1, 2, 3]]
EXTERNAL = [[7, 7, 7]]


def _make_service(last_chars):
    svc = DisplayService()
    client = Mock()
    client._last_characters = last_chars
    svc.vb_client = client
    return svc, client


class TestExternalChangeDetection:
    def test_differing_read_marks_out_of_band(self):
        """A fresh read that differs from what we last sent = external write."""
        svc, client = _make_service(SENT)
        client.read_current_message.return_value = EXTERNAL

        svc._poll_board_state_once()

        assert svc.is_showing_out_of_band() is True

    def test_matching_read_does_not_mark_out_of_band(self):
        """Board showing exactly what we sent — nothing external happened."""
        svc, client = _make_service(SENT)
        client.read_current_message.return_value = SENT

        svc._poll_board_state_once()

        assert svc.is_showing_out_of_band() is False

    def test_poll_still_caches_board_state(self):
        """The poll's original job — caching the read — must be preserved."""
        svc, client = _make_service(SENT)
        client.read_current_message.return_value = EXTERNAL

        svc._poll_board_state_once()

        assert svc._polled_characters == EXTERNAL
        assert svc._polled_at is not None

    def test_never_sent_anything_is_not_out_of_band(self):
        """No baseline to compare against (fresh start) — stay quiet."""
        svc, client = _make_service(None)
        client.read_current_message.return_value = EXTERNAL

        svc._poll_board_state_once()

        assert svc.is_showing_out_of_band() is False

    def test_failed_read_changes_nothing(self):
        """A failed read must not touch cache or flag."""
        svc, client = _make_service(SENT)
        client.read_current_message.return_value = None

        svc._poll_board_state_once()

        assert svc._polled_characters is None
        assert svc.is_showing_out_of_band() is False

    def test_send_racing_the_read_skips_detection(self):
        """If a send lands while the read is in flight, the read is stale
        against the new baseline — skip detection for this cycle rather
        than raise a false alarm."""
        svc, client = _make_service(SENT)
        new_sent = [[4, 4, 4]]

        def read_and_race():
            # A concurrent send replaces the baseline mid-read.
            client._last_characters = new_sent
            return SENT  # the read reflects the pre-send board

        client.read_current_message.side_effect = read_and_race

        svc._poll_board_state_once()

        assert svc.is_showing_out_of_band() is False
        # The stale read is still cached (matches historical behavior).
        assert svc._polled_characters == SENT

    def test_poll_never_clears_an_existing_flag(self):
        """A matching read only proves the board shows our last write —
        which may itself be a manual out-of-band message (issue #1831)."""
        svc, client = _make_service(SENT)
        svc.mark_showing_out_of_band()
        client.read_current_message.return_value = SENT

        svc._poll_board_state_once()

        assert svc.is_showing_out_of_band() is True
