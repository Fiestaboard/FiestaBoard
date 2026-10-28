"""The held-send store (issue #1944): typed, one per board, persisted, 24h TTL."""

from __future__ import annotations

import importlib
import json
import time

import pytest

from src import silence_queue
from src.silence_queue import HELD_TTL_SECONDS, HeldSend


@pytest.fixture(autouse=True)
def _clean_store():
    silence_queue.clear()
    yield
    silence_queue.clear()


def _store_file(tmp_path):
    # conftest points FIESTABOARD_DATA_DIR at tmp_path / "data".
    return tmp_path / "data" / "silence_held.json"


def test_hold_then_peek_returns_the_held_send(tmp_path):
    silence_queue.hold(HeldSend.text("GOOD MORNING", board_id="b1"))
    held = silence_queue.peek("b1")
    assert held is not None
    assert (held.kind, held.payload, held.board_id) == ("text", "GOOD MORNING", "b1")


def test_peek_does_not_consume_the_entry():
    silence_queue.hold(HeldSend.text("HI", board_id="b1"))
    silence_queue.peek("b1")
    assert silence_queue.peek("b1") is not None


def test_newest_hold_wins_per_board():
    silence_queue.hold(HeldSend.text("FIRST", board_id="b1"))
    silence_queue.hold(HeldSend.page("weather", board_id="b1"))
    held = silence_queue.peek("b1")
    assert (held.kind, held.payload) == ("page", "weather")


def test_boards_are_held_independently():
    silence_queue.hold(HeldSend.text("ONE", board_id="b1"))
    silence_queue.hold(HeldSend.text("TWO", board_id="b2"))
    assert silence_queue.peek("b1").payload == "ONE"
    assert silence_queue.peek("b2").payload == "TWO"


def test_discard_reports_whether_anything_was_held():
    silence_queue.hold(HeldSend.text("HI", board_id="b1"))
    assert silence_queue.discard("b1") is True
    assert silence_queue.peek("b1") is None
    assert silence_queue.discard("b1") is False


def test_hold_is_written_to_the_data_dir(tmp_path):
    silence_queue.hold(HeldSend.lines(["A", "B"], board_id="b1"))
    stored = json.loads(_store_file(tmp_path).read_text())
    assert stored["b1"]["kind"] == "lines"
    assert stored["b1"]["payload"] == ["A", "B"]


def test_store_survives_a_fresh_module_import(tmp_path):
    silence_queue.hold(HeldSend.grid([[1, 2]], board_id="b1", cells=None))
    reloaded = importlib.reload(silence_queue)
    try:
        held = reloaded.peek("b1")
        assert held is not None
        assert (held.kind, held.payload) == ("grid", {"characters": [[1, 2]], "cells": None})
    finally:
        importlib.reload(silence_queue)


def test_stale_entries_are_dropped_on_load(tmp_path):
    _store_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    stale = time.time() - HELD_TTL_SECONDS - 5
    _store_file(tmp_path).write_text(
        json.dumps(
            {
                "b1": {"kind": "text", "payload": "OLD", "board_id": "b1", "queued_at": stale},
                "b2": {"kind": "text", "payload": "NEW", "board_id": "b2", "queued_at": time.time()},
            }
        )
    )
    silence_queue._reset_for_tests()
    assert silence_queue.peek("b1") is None
    assert silence_queue.peek("b2").payload == "NEW"
    assert "b1" not in json.loads(_store_file(tmp_path).read_text())


def test_an_entry_that_goes_stale_after_load_is_dropped_on_peek(monkeypatch):
    silence_queue.hold(HeldSend.text("HI", board_id="b1"))
    real = time.time()
    monkeypatch.setattr(silence_queue.time, "time", lambda: real + HELD_TTL_SECONDS + 1)
    assert silence_queue.peek("b1") is None


def test_a_corrupt_store_file_reads_as_empty(tmp_path):
    _store_file(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _store_file(tmp_path).write_text("{not json")
    silence_queue._reset_for_tests()
    assert silence_queue.peek("b1") is None


def test_an_empty_board_id_is_refused():
    with pytest.raises(ValueError):
        HeldSend.text("HI", board_id="")


@pytest.mark.parametrize(
    ("send", "expected"),
    [
        (HeldSend.text("GOOD MORNING EVERYONE HAVE A GREAT DAY TODAY", board_id="b"), "GOOD MORNING EVERYONE HAVE A…"),
        (HeldSend.text("SHORT", board_id="b"), "SHORT"),
        (HeldSend.lines(["HELLO", "", "WORLD"], board_id="b"), "HELLO WORLD"),
        (HeldSend.page("weather", board_id="b"), "Page: weather"),
        (HeldSend.display("weather", board_id="b"), "Display: weather"),
        (HeldSend.grid([[0]], board_id="b"), "Board pattern"),
    ],
)
def test_preview_text_is_short_and_readable(send, expected):
    preview = silence_queue.preview_text(send)
    assert preview == expected
    assert len(preview) <= 40
