"""The board poll remembers the last CONFIRMED external frame (issue #1945).

When another app writes to the board, the web banner offers "Save as page".
Before this, that chance closed the moment FiestaBoard repainted the board:
the poll cache then held FiestaBoard's own page, and the other app's content
was gone. The runtime now keeps the frame the poll confirmed as external
(``BoardRuntime.external_frame``) in the same branch that raises
``showing_out_of_band`` — and, unlike that flag, the engine's own sends must
not clear it. It is replaced by a newer confirmed write, cleared by
``DELETE /board/external-frame`` (and the web client's Restore), and served
for at most ``EXTERNAL_FRAME_TTL_SECONDS``.
"""

import asyncio
from unittest.mock import Mock

import pytest

import src.main as main_module
from src.main import EXTERNAL_FRAME_TTL_SECONDS, BoardRuntime, DisplayService
from tests.test_per_board_engine import _board, _drive, _page_service, _schedule_service, _service_with_runtimes

SENT = [[1, 2, 3]]
EXTERNAL = [[7, 7, 7]]
NEWER_EXTERNAL = [[9, 9, 9]]


def _make_service(last_chars=SENT):
    svc = DisplayService()
    client = Mock()
    svc.vb_client = client
    if last_chars is not None:
        svc._primary_runtime().output.frames.record_sent(last_chars)
    return svc, client


def _confirm_external(svc, client, chars=EXTERNAL):
    """Two mismatching polls against the same baseline: a confirmed external write."""
    client.read_current_message.return_value = chars
    svc._poll_board_state_once()
    svc._poll_board_state_once()


class TestPollStoresTheFrame:
    def test_confirmed_external_write_stores_the_frame(self):
        svc, client = _make_service()

        _confirm_external(svc, client)

        rt = svc._primary_runtime()
        assert rt.external_frame is not None
        frame, detected_at = rt.external_frame
        assert frame == EXTERNAL
        assert isinstance(detected_at, float)
        # A copy: later mutation of the read must not reach the stored frame.
        assert frame is not EXTERNAL
        assert frame[0] is not EXTERNAL[0]

    def test_single_mismatch_stores_nothing(self):
        svc, client = _make_service()
        client.read_current_message.return_value = EXTERNAL

        svc._poll_board_state_once()

        assert svc._primary_runtime().external_frame is None

    def test_matching_poll_keeps_the_frame(self):
        svc, client = _make_service()
        _confirm_external(svc, client)
        kept = svc._primary_runtime().external_frame

        client.read_current_message.return_value = SENT
        svc._poll_board_state_once()

        assert svc._primary_runtime().external_frame == kept

    def test_newer_external_write_replaces_the_frame(self, monkeypatch):
        svc, client = _make_service()
        monkeypatch.setattr(main_module.time, "time", lambda: 1_000.0)
        _confirm_external(svc, client)

        monkeypatch.setattr(main_module.time, "time", lambda: 2_000.0)
        _confirm_external(svc, client, NEWER_EXTERNAL)

        assert svc._primary_runtime().external_frame == (NEWER_EXTERNAL, 2_000.0)

    def test_reconfirming_the_same_write_keeps_its_first_time(self, monkeypatch):
        """The judge confirms a write that stays up again every other poll;
        "another app wrote at 11:42" must keep saying 11:42."""
        svc, client = _make_service()
        monkeypatch.setattr(main_module.time, "time", lambda: 1_000.0)
        _confirm_external(svc, client)

        monkeypatch.setattr(main_module.time, "time", lambda: 1_060.0)
        _confirm_external(svc, client)

        assert svc._primary_runtime().external_frame == (EXTERNAL, 1_000.0)

    def test_force_refresh_live_read_does_not_touch_the_frame(self):
        """A live read (GET /board/current-message?force=true, the post-send
        refresh) only primes the poll cache; it is not the poll's judgement."""
        from src.board_state import read_board_state_live

        svc, client = _make_service()
        _confirm_external(svc, client)
        kept = svc._primary_runtime().external_frame

        client.read_current_message.return_value = SENT
        state = asyncio.run(read_board_state_live(None, force=True, service=svc))

        assert state.characters == SENT
        assert svc._primary_runtime().polled_characters == SENT
        assert svc._primary_runtime().external_frame == kept


class TestEngineRepaintKeepsTheFrame:
    def test_engine_repaint_keeps_the_frame(self):
        """FiestaBoard putting its page back clears the out-of-band flag, but
        the frame stays: that is the whole point of remembering it."""
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)
        rt = svc.runtimes["b1"]
        rt.showing_out_of_band = True
        rt.external_frame = ([row[:] for row in EXTERNAL], 1_000.0)

        _drive(svc, boards, pages=_page_service({"pA": {"content": "ALPHA"}}), schedule=_schedule_service({"b1": "pA"}))

        assert rt.showing_out_of_band is False
        assert rt.external_frame == (EXTERNAL, 1_000.0)


class TestAccessor:
    def test_accessor_returns_the_frame(self):
        svc, client = _make_service()
        _confirm_external(svc, client)

        frame = svc.external_frame()

        assert frame is not None
        assert frame[0] == EXTERNAL

    def test_accessor_returns_none_after_ttl(self, monkeypatch):
        svc, client = _make_service()
        monkeypatch.setattr(main_module.time, "time", lambda: 10_000.0)
        _confirm_external(svc, client)

        monkeypatch.setattr(main_module.time, "time", lambda: 10_000.0 + EXTERNAL_FRAME_TTL_SECONDS + 1)

        assert svc.external_frame() is None
        # The stale tuple is dropped, not kept around.
        assert svc._primary_runtime().external_frame is None

    def test_accessor_serves_a_frame_just_inside_the_ttl(self, monkeypatch):
        svc, client = _make_service()
        monkeypatch.setattr(main_module.time, "time", lambda: 10_000.0)
        _confirm_external(svc, client)

        monkeypatch.setattr(main_module.time, "time", lambda: 10_000.0 + EXTERNAL_FRAME_TTL_SECONDS)

        assert svc.external_frame() == (EXTERNAL, 10_000.0)

    def test_accessor_is_none_for_a_board_without_a_frame(self):
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)
        svc.runtimes["b1"].external_frame = (EXTERNAL, 1.0)

        assert svc.external_frame("b2") is None

    def test_accessor_resolves_the_named_board(self, monkeypatch):
        monkeypatch.setattr(main_module.time, "time", lambda: 5.0)
        boards = [_board("b1", "One"), _board("b2", "Two", port=7001)]
        svc, _clients = _service_with_runtimes(boards)
        svc.runtimes["b2"].external_frame = (EXTERNAL, 1.0)

        assert svc.external_frame("b2") == (EXTERNAL, 1.0)
        assert svc.external_frame("b1") is None

    def test_accessor_is_none_for_an_unknown_board(self):
        boards = [_board("b1", "One")]
        svc, _clients = _service_with_runtimes(boards)

        with pytest.MonkeyPatch.context() as mp:
            settings = Mock()
            settings.get_primary_board_id.return_value = "b1"
            mp.setattr("src.main.get_settings_service", lambda: settings)
            assert svc.external_frame("nope") is None

    def test_runtime_starts_without_a_frame(self):
        assert BoardRuntime(client=None, board_id="b1").external_frame is None
