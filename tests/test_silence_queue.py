"""Held intentions survive restart without consuming or mixing board state."""

import importlib
import importlib.util
import json
from dataclasses import replace

import pytest


def _queue():
    assert importlib.util.find_spec("src.silence_queue") is not None, "Held-send persistence is not implemented"
    return importlib.import_module("src.silence_queue")


def test_restart_keeps_newest_intent_for_each_board():
    queue = _queue()
    queue.hold(queue.HeldSend.text("OLD", board_id="a"))
    queue.hold(queue.HeldSend.page("page-later", board_id="b"))
    queue.hold(queue.HeldSend.text("NEW", board_id="a"))
    importlib.reload(queue)
    assert queue.peek("a").payload == "NEW"
    assert queue.peek("b").payload == "page-later"
    assert queue.peek("b").kind == "page"
    assert queue.peek("a").payload == "NEW"  # peek never consumes
    assert queue.discard("a") is True
    assert queue.discard("a") is False
    importlib.reload(queue)
    assert queue.peek("a") is None
    assert queue.peek("b").payload == "page-later"


@pytest.mark.parametrize("restart", [False, True])
def test_expiration_drops_old_intent_without_touching_fresh_board(monkeypatch, restart):
    queue = _queue()
    monkeypatch.setattr(queue.time, "time", lambda: 100000.0)
    queue.hold(queue.HeldSend.text("OLD", board_id="a"))
    queue.hold(replace(queue.HeldSend.text("FRESH", board_id="b"), queued_at=186399.0))
    monkeypatch.setattr(queue.time, "time", lambda: 186401.0)
    if restart:
        importlib.reload(queue)
    assert queue.peek("a") is None
    assert queue.peek("b").payload == "FRESH"


@pytest.mark.parametrize("raw", ["not json", "[]", '{"a":null}', '{"a":{"kind":"text"}}'])
def test_bad_file_does_not_prevent_new_holds(raw):
    queue = _queue()
    from src.paths import get_data_dir

    (get_data_dir() / "silence_held.json").write_text(raw)
    importlib.reload(queue)
    assert queue.peek("a") is None
    queue.hold(queue.HeldSend.text("RECOVERED", board_id="a"))
    importlib.reload(queue)
    assert queue.peek("a").payload == "RECOVERED"


@pytest.mark.parametrize(
    "changes",
    [
        {"board_id": "other"},
        {"kind": "unknown"},
        {"queued_at": "nonsense"},
        {"queued_at": float("nan")},
        {"queued_at": float("inf")},
        {"queued_at": 1e300},
        {"queued_at": 10**400},
        {"kind": "lines", "payload": 42},
        {"kind": "grid", "payload": None},
        {"kind": "text", "payload": []},
    ],
)
def test_malformed_record_does_not_hide_valid_board(changes):
    queue = _queue()
    from src.paths import get_data_dir

    record = {"kind": "text", "payload": "HELLO", "board_id": "a", "queued_at": queue.time.time()}
    record.update(changes)
    good = {"kind": "text", "payload": "GOOD", "board_id": "b", "queued_at": queue.time.time()}
    (get_data_dir() / "silence_held.json").write_text(json.dumps({"a": record, "b": good}))
    importlib.reload(queue)
    assert queue.peek("a") is None
    assert queue.peek("b").payload == "GOOD"


@pytest.mark.parametrize(
    "kind,payload,preview",
    [
        ("text", "HELLO   WORLD", "HELLO WORLD"),
        ("lines", ["HELLO", "WORLD"], "HELLO WORLD"),
        ("grid", [[1, 2]], "Board pattern"),
        ("display", "weather", "Display: weather"),
    ],
)
def test_typed_intents_keep_payload_and_preview(kind, payload, preview):
    queue = _queue()
    send = getattr(queue.HeldSend, kind)(payload, board_id="a")
    queue.hold(send)
    importlib.reload(queue)
    restored = queue.peek("a")
    assert restored.kind == kind
    assert queue.preview_text(restored) == preview
    assert restored.payload == ({"characters": payload, "cells": None} if kind == "grid" else payload)


def test_page_preview_uses_current_saved_name(monkeypatch):
    queue = _queue()
    from types import SimpleNamespace

    import src.pages.service

    monkeypatch.setattr(
        src.pages.service,
        "get_page_service",
        lambda: SimpleNamespace(get_page=lambda _: SimpleNamespace(name="WEATHER")),
    )
    assert queue.preview_text(queue.HeldSend.page("page-1", board_id="a")) == "Page: WEATHER"


def test_unknown_board_never_consumes_other_intents():
    queue = _queue()
    queue.hold(queue.HeldSend.text("KEEP", board_id="a"))
    assert queue.peek(None) is None
    assert queue.peek("missing") is None
    assert queue.discard(None) is False
    assert queue.discard("missing") is False
    assert queue.peek("a").payload == "KEEP"


def test_long_preview_is_short_and_readable():
    queue = _queue()
    assert (
        queue.preview_text(queue.HeldSend.text("ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE", board_id="a"))
        == "ONE TWO THREE FOUR FIVE SIX…"
    )
