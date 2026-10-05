"""Core owns each board's frame cache: dedupe, last-frame store, write detection.

The dedupe cache ("what the board shows"), the last-frame store ("what
FiestaBoard last sent, and when") and external-write detection used to be
private attributes of each board client that the engine and the API routes
peeked at. They now live on the board's ``OutputRuntime``:

- every client kind dedupes against, and records into, its runtime's cache;
- the last-frame store is written on every successful device write and on
  nothing else, and a dedupe clear never blanks it;
- a client's cache follows it onto the runtime that binds it, and a virtual
  board's runtimes share one "glass" per board id;
- external-write detection is a runtime method over that cache.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
import requests

from src.board_client import BoardClient
from src.main import BoardRuntime
from src.note_array_local_client import NoteArrayLocalClient
from src.outputs import FrameCache, OutputRuntime
from src.virtual_board_client import VirtualBoardClient

FLAGSHIP = (6, 22)


def _grid(fill: int, shape: tuple[int, int] = FLAGSHIP) -> list[list[int]]:
    rows, cols = shape
    return [[fill] * cols for _ in range(rows)]


def _ok_response() -> Mock:
    response = Mock()
    response.raise_for_status.return_value = None
    return response


# --- the cache itself -----------------------------------------------------------


class TestFrameCache:
    def test_a_successful_send_fills_the_dedupe_cache_and_the_store(self):
        frames = FrameCache()
        frames.record_sent(_grid(1), at=42.0)
        assert frames.matches(_grid(1))
        assert (frames.last_frame, frames.last_sent_at) == (_grid(1), 42.0)

    def test_forgetting_clears_the_dedupe_cache_but_keeps_the_last_frame(self):
        frames = FrameCache()
        frames.record_sent(_grid(1), at=42.0)
        frames.forget()
        assert frames.characters is None
        assert (frames.last_frame, frames.last_sent_at) == (_grid(1), 42.0)

    def test_a_read_back_syncs_the_dedupe_cache_but_was_never_sent(self):
        frames = FrameCache()
        frames.record_read(_grid(3))
        assert frames.matches(_grid(3))
        assert (frames.last_frame, frames.last_sent_at) == (None, None)

    def test_a_text_send_leaves_no_known_grid(self):
        frames = FrameCache()
        frames.record_sent(_grid(1))
        frames.record_text_sent("HELLO")
        assert frames.characters is None
        assert frames.matches_text("HELLO")

    def test_every_replacement_advances_the_generation(self):
        frames = FrameCache()
        seen = [frames.generation]
        frames.record_sent(_grid(1))
        seen.append(frames.generation)
        frames.record_read(_grid(1))
        seen.append(frames.generation)
        frames.forget()
        seen.append(frames.generation)
        assert seen == sorted(set(seen)), seen

    def test_grids_are_copied_on_the_way_in(self):
        frames = FrameCache()
        sent = _grid(1)
        frames.record_sent(sent)
        sent[0][0] = 9
        assert frames.characters[0][0] == 1
        assert frames.last_frame[0][0] == 1


# --- external-write detection ---------------------------------------------------


class TestObserveRead:
    def _runtime(self, sent=None) -> OutputRuntime:
        runtime = OutputRuntime("b1")
        if sent is not None:
            runtime.frames.record_sent(sent)
        return runtime

    def test_one_mismatch_is_only_a_suspect(self):
        runtime = self._runtime(_grid(1))
        assert runtime.observe_read(lambda: _grid(7)) == (_grid(7), False)
        assert runtime.external_write_suspected is True

    def test_a_second_mismatch_against_the_same_cache_is_an_external_write(self):
        runtime = self._runtime(_grid(1))
        runtime.observe_read(lambda: _grid(7))
        assert runtime.observe_read(lambda: _grid(7)) == (_grid(7), True)
        assert runtime.external_write_suspected is False

    def test_a_send_between_the_mismatches_restarts_the_cycle(self):
        runtime = self._runtime(_grid(1))
        runtime.observe_read(lambda: _grid(7))
        runtime.frames.record_sent(_grid(2))
        assert runtime.observe_read(lambda: _grid(7)) == (_grid(7), False)
        assert runtime.observe_read(lambda: _grid(7)) == (_grid(7), True)

    def test_a_send_racing_the_read_proves_nothing(self):
        runtime = self._runtime(_grid(1))
        runtime.observe_read(lambda: _grid(7))

        def read_while_a_send_lands():
            runtime.frames.record_sent(_grid(2))
            return _grid(7)

        assert runtime.observe_read(read_while_a_send_lands) == (_grid(7), False)
        assert runtime.external_write_suspected is False

    def test_a_matching_read_clears_the_suspect(self):
        runtime = self._runtime(_grid(1))
        runtime.observe_read(lambda: _grid(7))
        assert runtime.observe_read(lambda: _grid(1)) == (_grid(1), False)
        assert runtime.external_write_suspected is False

    def test_nothing_sent_means_nothing_to_judge(self):
        runtime = self._runtime()
        runtime.observe_read(lambda: _grid(7))
        assert runtime.observe_read(lambda: _grid(7)) == (_grid(7), False)

    def test_a_failed_read_changes_nothing(self):
        runtime = self._runtime(_grid(1))
        runtime.observe_read(lambda: _grid(7))
        assert runtime.observe_read(lambda: None) == (None, False)
        assert runtime.external_write_suspected is True


# --- binding --------------------------------------------------------------------


class TestBinding:
    def test_the_runtime_adopts_what_the_client_already_knew(self):
        client = BoardClient(api_key="test_key", host="192.0.2.10")
        with patch("src.board_client.requests.get") as get:
            get.return_value.json.return_value = {"message": _grid(4)}
            client.read_current_message(sync_cache=True)

        rt = BoardRuntime(client=client, board_id="b1")

        assert rt.output.frames.matches(_grid(4))

    def test_a_client_dedupes_against_its_bound_runtime(self):
        client = BoardClient(api_key="test_key", host="192.0.2.10")
        rt = BoardRuntime(client=client, board_id="b1")
        rt.output.frames.record_read(_grid(4))
        with patch("src.board_client.requests.post") as post:
            assert client.send_characters(_grid(4)) == (True, False)
        post.assert_not_called()


# --- the last-frame store, per client kind --------------------------------------


def _local():
    return BoardClient(api_key="test_key", host="192.0.2.10"), (6, 22)


def _rw_cloud():
    return BoardClient(api_key="test_key", use_cloud=True), (6, 22)


def _note_array_cloud():
    client = BoardClient(
        api_key="test_token", use_cloud=True, note_array_token="test_token", notes_wide=2, notes_tall=1
    )
    return client, (3, 30)


def _note_array_local():
    tiles = [
        {"row": 0, "col": 0, "host": "192.0.2.11", "local_api_key": "test_key"},
        {"row": 0, "col": 1, "host": "192.0.2.12", "local_api_key": "test_key"},
    ]
    return NoteArrayLocalClient(tiles, 2, 1), (3, 30)


def _virtual():
    return VirtualBoardClient(device_type="flagship"), (6, 22)


HTTP_KINDS = {
    "vestaboard-local": _local,
    "vestaboard-rw-cloud": _rw_cloud,
    "vestaboard-note-array-cloud": _note_array_cloud,
    "note-array-local": _note_array_local,
}
ALL_KINDS = {**HTTP_KINDS, "virtual": _virtual}


class TestLastFrameStore:
    @pytest.mark.parametrize("kind", list(ALL_KINDS))
    def test_every_successful_send_is_stored_with_its_time(self, kind):
        client, shape = ALL_KINDS[kind]()
        rt = BoardRuntime(client=client, board_id="b1")
        with patch("src.board_client.requests.post", return_value=_ok_response()):
            assert client.send_characters(_grid(1, shape)) == (True, True)
        assert rt.output.last_frame == _grid(1, shape)
        assert rt.output.last_sent_at is not None

    @pytest.mark.parametrize("kind", list(HTTP_KINDS))
    def test_a_failed_send_is_not_stored(self, kind):
        client, shape = HTTP_KINDS[kind]()
        rt = BoardRuntime(client=client, board_id="b1")
        with patch("src.board_client.requests.post", side_effect=requests.exceptions.HTTPError("500")):
            ok, sent = client.send_characters(_grid(1, shape))
        assert (ok, sent) == (False, False)
        assert rt.output.last_frame is None

    @pytest.mark.parametrize("kind", ["vestaboard-rw-cloud", "vestaboard-note-array-cloud"])
    def test_a_throttled_send_is_not_stored(self, kind):
        client, shape = HTTP_KINDS[kind]()
        rt = BoardRuntime(client=client, board_id="b1")
        with patch("src.board_client.requests.post", return_value=_ok_response()):
            client.send_characters(_grid(1, shape))
            outcome = client.send_characters(_grid(2, shape), with_outcome=True)
        assert outcome.throttled is True
        assert rt.output.last_frame == _grid(1, shape)

    @pytest.mark.parametrize("kind", list(ALL_KINDS))
    def test_clearing_the_dedupe_cache_keeps_the_last_frame(self, kind):
        client, shape = ALL_KINDS[kind]()
        rt = BoardRuntime(client=client, board_id="b1")
        with patch("src.board_client.requests.post", return_value=_ok_response()):
            client.send_characters(_grid(1, shape))
        client.clear_cache()
        assert rt.output.frames.characters is None
        assert rt.output.last_frame == _grid(1, shape)

    def test_an_engine_render_lands_in_the_board_runtimes_store(self):
        client, shape = _local()
        rt = BoardRuntime(client=client, board_id="b1")
        with patch("src.board_client.requests.post", return_value=_ok_response()):
            client.render(_grid(6, shape))
        assert rt.output.last_frame == _grid(6, shape)
