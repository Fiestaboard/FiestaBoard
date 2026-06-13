"""Tests for adaptive post-send board state refresh.

After a send, ``DisplayService.request_board_refresh`` should poll the
board on a short ramp (initial small delay, then short retry intervals,
capped at a max total) and stop as soon as the read result matches the
characters that were just sent. The latest read is always cached so the
display cache improves even when we never see a match.
"""

import time
from unittest.mock import Mock

from src.main import DisplayService

# Short timings so tests don't sleep for real seconds. The behavior
# under test is the *shape* of the retry loop — initial delay, retry
# cadence, total budget, early-stop on match — not the exact production
# constants.
INITIAL = 0.02
RETRY = 0.02
MAX_TOTAL = 0.20


def _make_service_with_last(last_chars):
    svc = DisplayService()
    client = Mock()
    client._last_characters = last_chars
    svc.vb_client = client
    return svc, client


def _wait_for_thread(svc, timeout=2.0):
    """Wait for the post-send refresh thread to finish."""
    thread = svc._refresh_thread
    assert thread is not None, "request_board_refresh should have started a thread"
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "refresh thread should complete within timeout"


class TestAdaptiveRefresh:
    def test_stops_when_first_read_matches_sent(self):
        """If the first read matches what we sent, no retries — one call."""
        sent = [[1, 2, 3]]
        svc, client = _make_service_with_last(sent)
        client.read_current_message.return_value = sent

        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc)

        assert client.read_current_message.call_count == 1
        assert svc._polled_characters == sent

    def test_retries_until_match(self):
        """If first read is stale, keep polling until it matches sent state."""
        sent = [[9, 9, 9]]
        stale = [[0, 0, 0]]
        svc, client = _make_service_with_last(sent)
        # Return stale twice, then the real (matching) state.
        client.read_current_message.side_effect = [stale, stale, sent, sent]

        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc)

        assert client.read_current_message.call_count == 3
        assert svc._polled_characters == sent

    def test_caches_latest_read_on_timeout(self):
        """When the board never matches, we still keep the freshest read."""
        sent = [[5, 5, 5]]
        latest = [[7, 7, 7]]
        svc, client = _make_service_with_last(sent)
        client.read_current_message.return_value = latest

        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc)

        # At least one retry must have happened (timeout window > initial).
        assert client.read_current_message.call_count >= 2
        # Even without a match, the latest read wins the cache.
        assert svc._polled_characters == latest

    def test_total_time_bounded_by_max_total(self):
        """The refresh thread must respect max_total_seconds, even on no-match."""
        sent = [[1]]
        not_sent = [[2]]
        svc, client = _make_service_with_last(sent)
        client.read_current_message.return_value = not_sent

        start = time.monotonic()
        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc, timeout=MAX_TOTAL + 1.0)
        elapsed = time.monotonic() - start

        # Allow a small fudge for thread scheduling, but not more than 2x.
        assert elapsed < MAX_TOTAL * 2, f"refresh exceeded budget: {elapsed:.3f}s"

    def test_cancels_previous_refresh(self):
        """A second request_board_refresh aborts the first in-flight cycle."""
        sent_a = [[10]]
        sent_b = [[20]]
        svc, client = _make_service_with_last(sent_a)
        client.read_current_message.return_value = sent_b

        svc.request_board_refresh(
            initial_delay_seconds=0.10,
            retry_interval_seconds=0.10,
            max_total_seconds=1.0,
        )
        first_thread = svc._refresh_thread

        # Immediately update the client's last-sent and trigger a new refresh.
        client._last_characters = sent_b
        time.sleep(0.01)  # let the first thread start sleeping
        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        second_thread = svc._refresh_thread

        # First thread should be cancelled and exit promptly without running
        # its retry loop to completion.
        first_thread.join(timeout=0.5)
        assert not first_thread.is_alive(), "previous refresh should have been cancelled"

        # Second cycle should still complete normally and leave a fresh cache.
        second_thread.join(timeout=2.0)
        assert not second_thread.is_alive()
        assert svc._polled_characters == sent_b

    def test_handles_read_returning_none(self):
        """``read_current_message`` returning None must not crash the loop."""
        sent = [[1]]
        svc, client = _make_service_with_last(sent)
        client.read_current_message.return_value = None

        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc)

        # We retried — None never matches "sent" so we keep going.
        assert client.read_current_message.call_count >= 2
        # No fresh state was successfully read; cache stays unchanged.
        assert svc._polled_characters is None

    def test_handles_read_exception(self):
        """A raised exception during read must not kill the loop."""
        sent = [[1]]
        svc, client = _make_service_with_last(sent)
        client.read_current_message.side_effect = RuntimeError("boom")

        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc)

        # Multiple attempts despite raising.
        assert client.read_current_message.call_count >= 2

    def test_handles_no_last_characters(self):
        """If we have no record of what we sent, still refresh — just no early stop."""
        svc, client = _make_service_with_last(None)
        latest = [[42]]
        client.read_current_message.return_value = latest

        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        _wait_for_thread(svc)

        # Without a target, we run the full window.
        assert client.read_current_message.call_count >= 2
        assert svc._polled_characters == latest

    def test_no_vb_client_is_noop(self):
        """No board client → no thread crash; call returns cleanly."""
        svc = DisplayService()
        svc.vb_client = None
        # Should not raise.
        svc.request_board_refresh(
            initial_delay_seconds=INITIAL,
            retry_interval_seconds=RETRY,
            max_total_seconds=MAX_TOTAL,
        )
        # Either no thread was started or it exits quickly.
        thread = svc._refresh_thread
        if thread is not None:
            thread.join(timeout=0.5)
            assert not thread.is_alive()
