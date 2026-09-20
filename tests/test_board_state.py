"""Unit tests for ``src/board_state.py`` — the one "what is on the board" reader (#1912).

Each test pins one rule of the selection order documented in the module:
which cache answers for which intent (``want="board"`` vs ``want="sent"``),
when a live read is permitted and where it runs, and what the caller gets
when nothing is known. The route/tool contracts built on top are pinned by
value in ``tests/test_board_state_contract.py``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from src.board_state import BoardReadError, read_board_state, read_board_state_live
from src.main import BoardRuntime, DisplayService
from tests.board_state_fakes import FLAGSHIP, NOTE, PhysicalClient, Runtime, Service, grid, virtual

SETTINGS = "src.display_runtime.get_settings_service"
TO_THREAD = "src.board_state.asyncio.to_thread"

POLLED = grid(FLAGSHIP, 2)
SENT = grid(FLAGSHIP, 1)
LIVE = grid(FLAGSHIP, 3)
NOTE_FRAME = grid(NOTE, 8)
POLLED_AT = 1_700_000_000.0


@pytest.fixture(autouse=True)
def primary_is_b1():
    settings = Mock()
    settings.get_primary_board_id.return_value = "b1"
    with patch(SETTINGS, return_value=settings):
        yield settings


def _live(board_id, *, service, force=False):
    return asyncio.run(read_board_state_live(board_id, force=force, service=service))


def _no_thread_hop():
    """Fail the test if the reader hops to a worker thread."""
    return patch(TO_THREAD, side_effect=AssertionError("hopped to a worker thread for a cache lookup"))


# ---------------------------------------------------------------------------
# want="board": what the board shows — the poll cache answers first
# ---------------------------------------------------------------------------


def test_board_wants_the_poll_cache_first_with_its_poll_time():
    service = Service({"b1": Runtime(PhysicalClient(last_sent=SENT, live=LIVE), polled=POLLED, polled_at=POLLED_AT)})

    state = read_board_state(None, want="board", service=service)

    assert (state.source, state.characters, state.polled_at) == ("polled", POLLED, POLLED_AT)
    assert state.expected_characters == SENT


def test_board_wants_a_secondary_boards_poll_cache_over_its_last_sent_cache():
    service = Service(
        {
            "b1": Runtime(PhysicalClient()),
            "b2": Runtime(PhysicalClient(last_sent=SENT), polled=POLLED, polled_at=POLLED_AT),
        }
    )

    state = read_board_state("b2", want="board", service=service)

    assert (state.source, state.characters) == ("polled", POLLED)


def test_board_falls_back_to_what_was_last_sent_without_a_poll_cache():
    client = PhysicalClient(last_sent=SENT, live=LIVE)
    service = Service({"b1": Runtime(client)})

    state = read_board_state(None, want="board", service=service)

    assert (state.source, state.characters, state.polled_at) == ("last_sent", SENT, None)
    assert client.live_reads == 0


def test_board_wants_a_virtual_boards_memory_before_its_last_sent_cache():
    vclient = virtual("note", frame=NOTE_FRAME)
    vclient._state.last_characters = grid(NOTE, 1)  # dedupe cache drifted from the glass
    service = Service({"b1": Runtime(PhysicalClient()), "vb": Runtime(vclient)})

    state = read_board_state("vb", want="board", service=service)

    assert (state.source, state.characters, state.polled_at) == ("live", NOTE_FRAME, None)


def test_nothing_known_is_empty():
    service = Service({"b1": Runtime(PhysicalClient(live=LIVE))})

    state = read_board_state(None, want="board", service=service)

    assert (state.source, state.characters, state.polled_at) == ("empty", None, None)
    assert (state.rows, state.cols) == (0, 0)


# ---------------------------------------------------------------------------
# want="sent": what FiestaBoard last displayed/sent — never the poll cache
# ---------------------------------------------------------------------------


def test_sent_ignores_a_stale_poll_cache_on_a_virtual_primary():
    """A panel on the primary board must show the frame just written, not the
    frame the 30s poll last saw."""
    vclient = virtual("flagship", frame=grid(FLAGSHIP, 8))
    service = Service({"b1": Runtime(vclient, polled=grid(FLAGSHIP, 9), polled_at=POLLED_AT)})

    state = read_board_state("b1", want="sent", service=service)

    assert (state.source, state.characters) == ("live", grid(FLAGSHIP, 8))


def test_sent_ignores_a_stale_poll_cache_on_a_physical_primary():
    service = Service({"b1": Runtime(PhysicalClient(last_sent=SENT, live=LIVE), polled=POLLED, polled_at=POLLED_AT)})

    state = read_board_state(None, want="sent", service=service)

    assert (state.source, state.characters, state.polled_at) == ("last_sent", SENT, None)


def test_sent_never_reads_a_physical_board_live():
    client = PhysicalClient(live=LIVE)
    service = Service({"b1": Runtime(client)})

    state = read_board_state(None, want="sent", service=service)

    assert client.live_reads == 0
    assert state.source == "empty"


def test_a_virtual_boards_refused_stale_shape_frame_is_empty_not_last_sent():
    vclient = virtual("note", frame=NOTE_FRAME, displayed=grid(FLAGSHIP, 8), sent_at=42.0)
    service = Service({"b1": Runtime(PhysicalClient()), "vb": Runtime(vclient)})

    state = read_board_state("vb", want="sent", service=service)

    assert (state.source, state.characters) == ("empty", None)
    assert state.expected_characters == NOTE_FRAME, "the raw last-sent grid is still published for drift checks"
    assert state.last_sent_at == 42.0


def test_only_a_client_that_says_is_virtual_is_true_is_read_from_memory():
    """A Mock or proxy client has a truthy ``is_virtual`` attribute; that must
    not earn it a ``read_current_message`` call on the unauthenticated panel
    path."""
    proxy = Mock()
    proxy._last_characters = SENT
    service = Service({"b1": Runtime(proxy)})

    state = read_board_state(None, want="sent", service=service)

    proxy.read_current_message.assert_not_called()
    assert (state.source, state.characters) == ("last_sent", SENT)


# ---------------------------------------------------------------------------
# BoardState presentation fields
# ---------------------------------------------------------------------------


def test_api_mode_reflects_the_clients_connection():
    cloud = Service({"b1": Runtime(PhysicalClient(last_sent=SENT, use_cloud=True))})
    local = Service({"b1": Runtime(PhysicalClient(last_sent=SENT))})

    assert read_board_state(None, want="board", service=cloud).api_mode == "cloud"
    assert read_board_state(None, want="board", service=local).api_mode == "local"


def test_last_sent_at_is_published_whatever_answered():
    vclient = virtual("note", frame=NOTE_FRAME, sent_at=42.0)
    service = Service(
        {"b1": Runtime(PhysicalClient()), "vb": Runtime(vclient, polled=grid(NOTE, 9), polled_at=POLLED_AT)}
    )

    state = read_board_state("vb", want="board", service=service)

    assert state.source == "polled"
    assert state.last_sent_at == 42.0


# ---------------------------------------------------------------------------
# Board resolution: the id's own runtime first
# ---------------------------------------------------------------------------


def test_an_id_with_its_own_runtime_is_served_from_it_even_when_settings_call_it_primary(primary_is_b1):
    """While settings and the engine disagree about which board is primary
    (a board was deleted, a rebuild is in flight), board 2's id must never
    answer with board 1's content."""
    primary_is_b1.get_primary_board_id.return_value = "b2"
    service = Service(
        {
            "b1": Runtime(PhysicalClient(), polled=grid(FLAGSHIP, 1), polled_at=POLLED_AT),
            "b2": Runtime(PhysicalClient(), polled=grid(NOTE, 2), polled_at=POLLED_AT),
        }
    )

    state = read_board_state("b2", want="board", service=service)

    assert state.characters == grid(NOTE, 2)


def test_the_primarys_own_id_falls_back_to_the_sentinel_keyed_primary_runtime():
    """Legacy installs key the primary runtime under ``__primary__`` (#1874)."""
    service = Service({"__primary__": Runtime(PhysicalClient(last_sent=SENT))}, primary_key="__primary__")

    state = read_board_state("b1", want="board", service=service)

    assert (state.source, state.characters) == ("last_sent", SENT)


def test_an_unknown_board_is_empty():
    service = Service({"b1": Runtime(PhysicalClient(last_sent=SENT), polled=POLLED)})

    state = read_board_state("no-such-board", want="board", service=service)

    assert state.board_id == "no-such-board"
    assert (state.source, state.characters, state.api_mode) == ("empty", None, "local")


def test_a_board_whose_runtime_has_no_client_is_empty():
    service = Service({"b1": Runtime(PhysicalClient()), "b2": Runtime(None)})

    assert read_board_state("b2", want="board", service=service).source == "empty"
    assert _live("b2", service=service, force=True).source == "empty"


def test_no_display_service_is_empty():
    assert read_board_state("b1", want="board", service=None).source == "empty"
    assert _live("b1", service=None).source == "empty"


# ---------------------------------------------------------------------------
# DisplayService.runtime_for — the resolution the fakes mirror
# ---------------------------------------------------------------------------


def _engine(runtimes: dict[str, BoardRuntime], primary_key: str | None) -> DisplayService:
    engine = DisplayService.__new__(DisplayService)
    engine.runtimes = runtimes
    engine._primary_board_id = primary_key
    return engine


def _runtime(board_id: str) -> BoardRuntime:
    return BoardRuntime(client=None, board_id=board_id)


def test_runtime_for_none_is_the_primary_runtime():
    b1 = _runtime("b1")
    engine = _engine({"b1": b1, "b2": _runtime("b2")}, "b1")

    assert engine.runtime_for(None) is b1


def test_runtime_for_prefers_the_ids_own_runtime_over_the_primary(primary_is_b1):
    primary_is_b1.get_primary_board_id.return_value = "b2"
    b2 = _runtime("b2")
    engine = _engine({"b1": _runtime("b1"), "b2": b2}, "b1")

    with patch("src.main.get_settings_service", return_value=primary_is_b1):
        assert engine.runtime_for("b2") is b2
    primary_is_b1.get_primary_board_id.assert_not_called()


def test_runtime_for_resolves_the_settings_primarys_id_to_a_sentinel_keyed_runtime(primary_is_b1):
    sentinel = _runtime("__primary__")
    engine = _engine({"__primary__": sentinel}, "__primary__")

    with patch("src.main.get_settings_service", return_value=primary_is_b1):
        assert engine.runtime_for("b1") is sentinel
        assert engine.runtime_for("b9") is None


def test_runtime_for_lets_a_settings_failure_propagate(primary_is_b1):
    primary_is_b1.get_primary_board_id.side_effect = RuntimeError("settings unreadable")
    engine = _engine({"__primary__": _runtime("__primary__")}, "__primary__")

    with patch("src.main.get_settings_service", return_value=primary_is_b1), pytest.raises(RuntimeError):
        engine.runtime_for("b1")


# ---------------------------------------------------------------------------
# The poll cache is read as one pair
# ---------------------------------------------------------------------------


class _RacingRuntime:
    """A runtime whose poll thread lands a new (characters, at) pair between
    the reader's first ``polled_at`` read and its ``polled_characters`` read —
    the poll thread writes the two fields in two statements."""

    client = None

    def __init__(self):
        self._at = 1.0
        self._chars = grid(FLAGSHIP, 1)
        self.at_reads = 0

    @property
    def polled_at(self):
        self.at_reads += 1
        return self._at

    @property
    def polled_characters(self):
        chars = self._chars
        if self.at_reads == 1:
            # The poll thread's write lands now: characters first, then at.
            self._chars = grid(FLAGSHIP, 2)
            self._at = 2.0
            return self._chars
        return chars


def test_the_poll_cache_is_read_as_a_matching_pair():
    rt = _RacingRuntime()
    service = SimpleNamespace(runtime_for=lambda board_id: rt)

    state = read_board_state(None, want="board", service=service)

    assert (state.characters, state.polled_at) == (grid(FLAGSHIP, 2), 2.0)


# ---------------------------------------------------------------------------
# read_board_state_live: a network read only where the poll cache cannot answer
# ---------------------------------------------------------------------------


def test_live_serves_a_populated_poll_cache_without_leaving_the_loop():
    client = PhysicalClient(live=LIVE)
    service = Service({"b1": Runtime(client, polled=POLLED, polled_at=POLLED_AT)})

    with _no_thread_hop():
        state = _live(None, service=service)

    assert client.live_reads == 0
    assert (state.source, state.characters, state.polled_at) == ("polled", POLLED, POLLED_AT)


def test_live_reads_the_board_off_the_loop_when_the_poll_cache_is_empty_and_primes_it():
    client = PhysicalClient(last_sent=SENT, live=LIVE)
    service = Service({"b1": Runtime(client)})

    with patch("src.board_state.time.time", return_value=123.0):
        state = _live(None, service=service)

    assert client.live_reads == 1
    assert (state.source, state.characters, state.polled_at) == ("live", LIVE, None)
    rt = service.runtimes["b1"]
    assert (rt.polled_characters, rt.polled_at) == (LIVE, 123.0)


def test_force_bypasses_a_populated_poll_cache():
    client = PhysicalClient(live=LIVE)
    service = Service({"b1": Runtime(client, polled=POLLED, polled_at=POLLED_AT)})

    state = _live(None, service=service, force=True)

    assert client.live_reads == 1
    assert (state.source, state.characters) == ("live", LIVE)
    assert service.runtimes["b1"].polled_characters == LIVE, "the forced read did not replace the poll cache"


def test_a_failed_live_read_raises_and_leaves_the_cache_alone():
    service = Service({"b1": Runtime(PhysicalClient(live=None), polled=POLLED, polled_at=POLLED_AT)})

    with pytest.raises(BoardReadError) as excinfo:
        _live(None, service=service, force=True)

    assert excinfo.value.board_id is None
    rt = service.runtimes["b1"]
    assert (rt.polled_characters, rt.polled_at) == (POLLED, POLLED_AT)


def test_a_failed_live_read_does_not_fall_back_to_what_was_last_sent():
    service = Service({"b1": Runtime(PhysicalClient(last_sent=SENT, live=None))})

    with pytest.raises(BoardReadError):
        _live(None, service=service)


def test_a_live_read_on_a_secondary_board_primes_that_boards_runtime():
    b2 = PhysicalClient(live=NOTE_FRAME)
    service = Service({"b1": Runtime(PhysicalClient()), "b2": Runtime(b2)})

    state = _live("b2", service=service)

    assert state.source == "live"
    assert service.runtimes["b2"].polled_characters == NOTE_FRAME
    assert service.runtimes["b1"].polled_characters is None, "the primary cache was primed with a secondary's grid"


def test_a_virtual_board_answers_from_memory_inline_and_primes_the_poll_cache():
    vclient = virtual("flagship", frame=grid(FLAGSHIP, 4))
    service = Service({"b1": Runtime(vclient)})

    with _no_thread_hop(), patch("src.board_state.time.time", return_value=123.0):
        state = _live(None, service=service, force=True)

    assert (state.source, state.characters, state.polled_at) == ("live", grid(FLAGSHIP, 4), None)
    rt = service.runtimes["b1"]
    assert (rt.polled_characters, rt.polled_at) == (grid(FLAGSHIP, 4), 123.0)


@pytest.mark.parametrize("force", [False, True], ids=["cache_empty", "forced"])
def test_a_virtual_boards_refusal_is_empty_not_a_failed_live_read(force):
    """A virtual primary with nothing displayed (or a stale-shape frame) is
    not a board that failed to answer: never BoardReadError, never a 503."""
    service = Service({"b1": Runtime(virtual("flagship", frame=grid(FLAGSHIP, 4), displayed=grid(NOTE, 4)))})

    with _no_thread_hop():
        state = _live(None, service=service, force=force)

    assert (state.source, state.characters) == ("empty", None)
    assert service.runtimes["b1"].polled_characters is None


# ---------------------------------------------------------------------------
# The routes call the reader inline
# ---------------------------------------------------------------------------


@pytest.fixture
def app_client(_isolated_data_dir):
    from src.api_server import app

    return TestClient(app)


def test_the_panel_frame_never_uses_the_send_pool(app_client):
    from src.panels.models import Panel

    vclient = virtual("note", frame=NOTE_FRAME)
    service = Service({"b1": Runtime(PhysicalClient()), "vb": Runtime(vclient)})
    panels = Mock()
    panels.get_panel_by_ref.return_value = Panel(name="Hall TV", board_id="vb")
    with (
        patch("src.panels.routes.get_panel_service", return_value=panels),
        patch("src.panels.routes.get_service", return_value=service),
        # Any use of the send pool acquires its executor first; refusing that
        # catches every route into it, however the pool is reached.
        patch(
            "src.board_send_executor._BoundedPool._get",
            side_effect=AssertionError("frame read went through the send pool"),
        ),
    ):
        response = app_client.get("/panel/abc123def456/frame")

    assert response.status_code == 200
    assert response.json()["characters"] == NOTE_FRAME


def test_current_message_serves_the_poll_cache_without_leaving_the_loop(app_client):
    service = Service({"b1": Runtime(PhysicalClient(live=LIVE), polled=POLLED, polled_at=POLLED_AT)})

    with patch("src.display_runtime.get_service", return_value=service), _no_thread_hop():
        response = app_client.get("/board/current-message")

    assert response.status_code == 200
    assert response.json()["characters"] == POLLED
