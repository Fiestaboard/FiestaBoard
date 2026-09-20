"""Unit tests for ``src/board_state.py`` — the one "what is on the board" reader (#1912).

Each test pins one rule of the selection order documented in the module:
which cache answers, in what order, when a live read is permitted, and what
the caller gets when nothing is known. The route/tool contracts built on top
are pinned by value in ``tests/test_board_state_contract.py``.
"""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock, patch

import pytest

from src.board_state import BoardReadError, read_board_state
from src.virtual_board_client import VirtualBoardClient

SETTINGS = "src.display_runtime.get_settings_service"
DISPLAY_SERVICE = "src.display_runtime.get_service"

POLLED = [[2] * 22 for _ in range(6)]
SENT = [[1] * 22 for _ in range(6)]
LIVE = [[3] * 22 for _ in range(6)]
NOTE_FRAME = [[8] * 15 for _ in range(3)]
POLLED_AT = 1_700_000_000.0


class _Client:
    is_virtual = False

    def __init__(self, *, last_sent=None, live=None, last_sent_at=None):
        self._last_characters = last_sent
        self._live = live
        self.live_reads = 0
        if last_sent_at is not None:
            self._last_sent_at = last_sent_at

    def read_current_message(self, sync_cache: bool = False):
        self.live_reads += 1
        return self._live


class _Runtime:
    def __init__(self, client=None, polled=None, polled_at=None):
        self.client = client
        self.polled_characters = polled
        self.polled_at = polled_at


class _Service:
    def __init__(self, runtimes: dict[str, _Runtime], primary_key: str = "b1"):
        self.runtimes = runtimes
        self._primary_key = primary_key

    @property
    def vb_client(self):
        rt = self.runtimes.get(self._primary_key)
        return rt.client if rt is not None else None

    @property
    def _polled_characters(self):
        rt = self.runtimes.get(self._primary_key)
        return rt.polled_characters if rt is not None else None

    @_polled_characters.setter
    def _polled_characters(self, value):
        self.runtimes[self._primary_key].polled_characters = value

    @property
    def _polled_at(self):
        rt = self.runtimes.get(self._primary_key)
        return rt.polled_at if rt is not None else None

    @_polled_at.setter
    def _polled_at(self, value):
        self.runtimes[self._primary_key].polled_at = value

    def get_runtime(self, board_id):
        return self.runtimes.get(board_id)


@pytest.fixture(autouse=True)
def primary_is_b1():
    settings = Mock()
    settings.get_primary_board_id.return_value = "b1"
    with patch(SETTINGS, return_value=settings):
        yield settings


# ---------------------------------------------------------------------------
# Source selection, one branch per test
# ---------------------------------------------------------------------------


def test_the_poll_cache_answers_first_with_its_poll_time():
    service = _Service({"b1": _Runtime(_Client(last_sent=SENT, live=LIVE), polled=POLLED, polled_at=POLLED_AT)})

    state = read_board_state(None, service=service)

    assert state.source == "polled"
    assert state.characters == POLLED
    assert state.timestamp == POLLED_AT
    assert state.expected_characters == SENT


def test_the_poll_cache_wins_over_the_last_sent_cache_for_a_secondary_board():
    service = _Service(
        {"b1": _Runtime(_Client()), "b2": _Runtime(_Client(last_sent=SENT), polled=POLLED, polled_at=POLLED_AT)}
    )

    state = read_board_state("b2", service=service)

    assert (state.source, state.characters) == ("polled", POLLED)


def test_what_was_last_sent_answers_when_there_is_no_poll_cache():
    client = _Client(last_sent=SENT, live=LIVE)
    service = _Service({"b1": _Runtime(client)})

    state = read_board_state(None, service=service)

    assert (state.source, state.characters) == ("last_sent", SENT)
    assert state.timestamp is None, "a physical client tracks no send time"
    assert client.live_reads == 0


def test_last_sent_carries_the_send_time_when_the_client_tracks_one():
    service = _Service({"b1": _Runtime(_Client(last_sent=SENT, last_sent_at=42.0))})

    state = read_board_state(None, service=service)

    assert state.source == "last_sent"
    assert state.timestamp == 42.0
    assert state.last_sent_at == 42.0


def test_nothing_known_is_empty():
    service = _Service({"b1": _Runtime(_Client(live=LIVE))})

    state = read_board_state(None, service=service)

    assert (state.source, state.characters, state.timestamp) == ("empty", None, None)
    assert (state.rows, state.cols) == (0, 0)


# ---------------------------------------------------------------------------
# Live reads: gated, forced, primed, failed
# ---------------------------------------------------------------------------


def test_a_physical_board_is_never_read_live_unless_allowed():
    client = _Client(live=LIVE)
    service = _Service({"b1": _Runtime(client)})

    state = read_board_state(None, service=service)

    assert client.live_reads == 0
    assert state.source == "empty"


def test_allow_live_reads_the_board_only_when_the_poll_cache_is_empty():
    client = _Client(live=LIVE)
    service = _Service({"b1": _Runtime(client, polled=POLLED, polled_at=POLLED_AT)})

    state = read_board_state(None, allow_live=True, service=service)

    assert client.live_reads == 0
    assert (state.source, state.characters) == ("polled", POLLED)


def test_allow_live_with_an_empty_poll_cache_reads_the_board_and_primes_the_cache():
    client = _Client(live=LIVE)
    service = _Service({"b1": _Runtime(client)})

    with patch("src.board_state.time.time", return_value=123.0):
        state = read_board_state(None, allow_live=True, service=service)

    assert client.live_reads == 1
    assert (state.source, state.characters, state.timestamp) == ("live", LIVE, 123.0)
    assert (service._polled_characters, service._polled_at) == (LIVE, 123.0)


def test_force_live_bypasses_a_populated_poll_cache():
    client = _Client(live=LIVE)
    service = _Service({"b1": _Runtime(client, polled=POLLED, polled_at=POLLED_AT)})

    state = read_board_state(None, force_live=True, service=service)

    assert client.live_reads == 1
    assert (state.source, state.characters) == ("live", LIVE)
    assert service._polled_characters == LIVE, "the forced read did not replace the poll cache"


def test_a_failed_live_read_raises_and_leaves_the_cache_alone():
    client = _Client(live=None)
    service = _Service({"b1": _Runtime(client, polled=POLLED, polled_at=POLLED_AT)})

    with pytest.raises(BoardReadError) as excinfo:
        read_board_state(None, force_live=True, service=service)

    assert excinfo.value.board_id is None
    assert (service._polled_characters, service._polled_at) == (POLLED, POLLED_AT)


def test_a_failed_live_read_does_not_fall_back_to_what_was_last_sent():
    service = _Service({"b1": _Runtime(_Client(last_sent=SENT, live=None))})

    with pytest.raises(BoardReadError):
        read_board_state(None, allow_live=True, service=service)


def test_a_live_read_on_a_secondary_board_primes_that_boards_runtime():
    b2 = _Client(live=NOTE_FRAME)
    service = _Service({"b1": _Runtime(_Client()), "b2": _Runtime(b2)})

    state = read_board_state("b2", allow_live=True, service=service)

    assert state.source == "live"
    assert service.runtimes["b2"].polled_characters == NOTE_FRAME
    assert service._polled_characters is None, "the primary cache was primed with a secondary board's grid"


# ---------------------------------------------------------------------------
# Virtual boards: memory is the board, and the shape guard is honoured
# ---------------------------------------------------------------------------


def test_a_virtual_board_answers_from_its_own_memory_without_allow_live():
    vclient = VirtualBoardClient(device_type="note")
    vclient.send_characters(NOTE_FRAME)
    service = _Service({"b1": _Runtime(_Client()), "vb": _Runtime(vclient)})

    state = read_board_state("vb", service=service)

    assert (state.source, state.characters) == ("live", NOTE_FRAME)
    assert state.last_sent_at == vclient._last_sent_at


def test_a_virtual_boards_refused_stale_shape_frame_is_empty_not_last_sent():
    vclient = VirtualBoardClient(device_type="note")
    vclient.send_characters(NOTE_FRAME)
    vclient._state.displayed_characters = [[8] * 22 for _ in range(6)]  # re-fit left an old-shape frame
    service = _Service({"b1": _Runtime(_Client()), "vb": _Runtime(vclient)})

    state = read_board_state("vb", service=service)

    assert (state.source, state.characters) == ("empty", None)
    assert state.expected_characters == NOTE_FRAME, "the raw last-sent grid is still published for drift checks"
    assert state.last_sent_at == vclient._last_sent_at


# ---------------------------------------------------------------------------
# Board resolution
# ---------------------------------------------------------------------------


def test_the_primary_boards_own_id_is_served_from_the_primary_caches():
    service = _Service({"b1": _Runtime(_Client(), polled=POLLED, polled_at=POLLED_AT)})

    by_id = read_board_state("b1", service=service)
    by_default = read_board_state(None, service=service)

    assert by_id.board_id == "b1"
    assert replace(by_id, board_id=None) == by_default


def test_a_sentinel_keyed_primary_runtime_still_answers_for_the_primarys_id():
    """Legacy installs key the primary runtime under ``__primary__`` (#1874)."""
    service = _Service({"__primary__": _Runtime(_Client(last_sent=SENT))}, primary_key="__primary__")

    state = read_board_state("b1", service=service)

    assert (state.source, state.characters) == ("last_sent", SENT)


def test_an_unknown_board_is_empty():
    service = _Service({"b1": _Runtime(_Client(last_sent=SENT), polled=POLLED)})

    state = read_board_state("no-such-board", service=service)

    assert state.board_id == "no-such-board"
    assert (state.source, state.characters, state.client) == ("empty", None, None)


def test_a_board_whose_runtime_has_no_client_is_empty():
    service = _Service({"b1": _Runtime(_Client()), "b2": _Runtime(None)})

    state = read_board_state("b2", allow_live=True, force_live=True, service=service)

    assert (state.source, state.characters) == ("empty", None)


def test_no_display_service_is_empty():
    assert read_board_state("b1", service=None).source == "empty"


def test_the_display_service_is_resolved_at_call_time_when_not_given():
    service = _Service({"b1": _Runtime(_Client(), polled=POLLED, polled_at=POLLED_AT)})

    with patch(DISPLAY_SERVICE, return_value=service):
        state = read_board_state()

    assert (state.source, state.characters) == ("polled", POLLED)


def test_unreadable_settings_treat_every_id_as_a_secondary_board(primary_is_b1):
    primary_is_b1.get_primary_board_id.side_effect = RuntimeError("settings unreadable")
    service = _Service({"b1": _Runtime(_Client(), polled=POLLED, polled_at=POLLED_AT)})

    state = read_board_state("b1", service=service)

    assert (state.source, state.characters) == ("polled", POLLED), "b1 has a runtime under its own id"
    assert read_board_state("b9", service=service).source == "empty"
