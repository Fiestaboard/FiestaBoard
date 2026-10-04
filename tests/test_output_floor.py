"""Core owns the send floor, keyed by the device a driver declares.

The 15 s floor (Vestaboard's documented Read/Write limit; the note-array
Cloud API's too) used to live in ``BoardClient``: per client *instance* for
RW Cloud, and in a module-level registry keyed by raw token for note arrays.
It now lives in core (``src/outputs/floor.py``), keyed by
``driver.device_key()`` — host+port for a local board, a hash of the key or
token for a cloud board — so it holds per *device*, whichever client object
sends:

- a board re-save rebuilds its client; the floor survives (deliberate for
  RW Cloud, which used to reset; note-array Cloud always survived);
- a throwaway client an API route builds for the same board (welcome, live
  render) sees the engine's floor (A4 finding 1);
- an upstream HTTP 429 is the device's own floor: reported as throttled,
  with the ``Retry-After`` it sent, and the slot is kept so an immediate
  retry is not POSTed a second later (A4 finding 2).
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

import src.board_client as board_client_module
from src.board_client import BoardClient
from src.note_array_local_client import NoteArrayLocalClient
from src.outputs.factory import build_driver
from src.virtual_board_client import VirtualBoardClient

FLAGSHIP = (6, 22)


def _grid(fill: int, shape: tuple[int, int] = FLAGSHIP) -> list[list[int]]:
    rows, cols = shape
    return [[fill] * cols for _ in range(rows)]


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    """Freeze the floor clock. Clients built after this read it."""
    fake = _Clock()
    monkeypatch.setattr(board_client_module, "_time_module", SimpleNamespace(monotonic=fake.monotonic))
    return fake


class _Wire:
    """Records POSTs and answers each with the next scripted response (200 by default)."""

    def __init__(self) -> None:
        self.posts: list[str] = []
        self.answers: list[requests.Response] = []

    def post(self, url, **_kwargs):
        self.posts.append(url)
        return self.answers.pop(0) if self.answers else _response(200)


def _response(status: int, headers: dict[str, str] | None = None) -> requests.Response:
    response = requests.Response()
    response.status_code = status
    response.headers.update(headers or {})
    response._content = b"{}"
    response.url = "https://rw.vestaboard.com/"
    return response


@pytest.fixture
def wire(monkeypatch) -> _Wire:
    recorder = _Wire()
    monkeypatch.setattr(requests, "post", recorder.post)
    monkeypatch.setattr(requests, "get", Mock(side_effect=AssertionError("no reads expected")))
    return recorder


def _rw_cloud(key: str) -> dict:
    return {"id": f"rw-{key}", "api_mode": "cloud", "device_type": "flagship", "cloud_key": key}


def _note_array_cloud(token: str) -> dict:
    return {
        "id": f"na-{token}",
        "api_mode": "cloud",
        "device_type": "note_array",
        "notes_wide": 2,
        "notes_tall": 1,
        "note_array_token": token,
    }


# --- the floor survives a client rebuild --------------------------------------------


def test_a_rebuilt_rw_cloud_client_is_still_inside_the_floor(clock, wire):
    """Deliberate change: a board re-save used to reset the RW Cloud window."""
    first = build_driver(_rw_cloud("test_rw_rebuild"))
    assert first.render(_grid(1), with_outcome=True).was_sent is True

    clock.t += 5.0
    rebuilt = build_driver(_rw_cloud("test_rw_rebuild"))
    outcome = rebuilt.render(_grid(2), with_outcome=True)

    assert (outcome.success, outcome.was_sent, outcome.throttled) == (True, False, True)
    assert outcome.retry_after_seconds == 10
    assert len(wire.posts) == 1


def test_a_rebuilt_note_array_cloud_client_is_still_inside_the_floor(clock, wire):
    """Parity: the note-array window always survived a rebuild."""
    first = build_driver(_note_array_cloud("test_na_rebuild"))
    assert first.render(_grid(1, (3, 30)), with_outcome=True).was_sent is True

    clock.t += 5.0
    rebuilt = build_driver(_note_array_cloud("test_na_rebuild"))
    outcome = rebuilt.render(_grid(2, (3, 30)), with_outcome=True)

    assert (outcome.was_sent, outcome.throttled, outcome.retry_after_seconds) == (False, True, 10)
    assert len(wire.posts) == 1


def test_two_rw_cloud_boards_keep_separate_floors(clock, wire):
    one = build_driver(_rw_cloud("test_rw_one"))
    two = build_driver(_rw_cloud("test_rw_two"))
    assert one.render(_grid(1), with_outcome=True).was_sent is True
    assert two.render(_grid(1), with_outcome=True).was_sent is True
    assert len(wire.posts) == 2


def test_the_floor_reopens_once_the_window_has_passed(clock, wire):
    first = build_driver(_rw_cloud("test_rw_reopen"))
    first.render(_grid(1), with_outcome=True)
    clock.t += 15.0
    rebuilt = build_driver(_rw_cloud("test_rw_reopen"))
    assert rebuilt.render(_grid(2), with_outcome=True).was_sent is True


# --- a throwaway client sees the engine's floor (A4 finding 1) ------------------------


def test_a_throwaway_client_for_the_same_board_sees_the_engines_floor(clock, wire):
    """The welcome and live-render routes build their own client per request."""
    from src.main import BoardRuntime

    board = _rw_cloud("test_rw_throwaway")
    engine = BoardRuntime(client=build_driver(board), board_id=board["id"])
    assert engine.client.render(_grid(1), with_outcome=True).was_sent is True

    clock.t += 3.0
    throwaway = build_driver(board)
    throwaway.skip_unchanged = False
    outcome = throwaway.render(_grid(2), force=True, with_outcome=True)

    assert (outcome.was_sent, outcome.throttled, outcome.retry_after_seconds) == (False, True, 12)
    assert len(wire.posts) == 1


# --- an upstream 429 is a throttle (A4 finding 2) -----------------------------------


def test_an_upstream_429_is_reported_as_throttled_with_its_retry_after(clock, wire):
    client = build_driver(_rw_cloud("test_rw_429_header"))
    wire.answers = [_response(429, {"Retry-After": "30"})]

    outcome = client.render(_grid(1), with_outcome=True)

    assert (outcome.success, outcome.was_sent, outcome.throttled) == (True, False, True)
    assert outcome.retry_after_seconds == 30
    assert client.last_send_throttled is True


def test_an_upstream_429_without_retry_after_reports_the_floor(clock, wire):
    client = build_driver(_rw_cloud("test_rw_429_bare"))
    wire.answers = [_response(429)]

    outcome = client.render(_grid(1), with_outcome=True)

    assert (outcome.throttled, outcome.retry_after_seconds) == (True, 15)


def test_an_immediate_retry_after_a_429_is_not_posted(clock, wire):
    """The 429 keeps the floor slot: a retry 1 s later is throttled locally."""
    client = build_driver(_rw_cloud("test_rw_429_retry"))
    wire.answers = [_response(429)]
    client.render(_grid(1), with_outcome=True)

    clock.t += 1.0
    outcome = client.render(_grid(1), with_outcome=True)

    assert (outcome.was_sent, outcome.throttled, outcome.retry_after_seconds) == (False, True, 14)
    assert len(wire.posts) == 1


def test_a_retry_after_longer_than_the_floor_holds_the_device_that_long(clock, wire):
    client = build_driver(_rw_cloud("test_rw_429_long"))
    wire.answers = [_response(429, {"Retry-After": "40"})]
    client.render(_grid(1), with_outcome=True)

    clock.t += 20.0
    outcome = client.render(_grid(1), with_outcome=True)

    assert (outcome.was_sent, outcome.throttled, outcome.retry_after_seconds) == (False, True, 20)
    clock.t += 20.0
    assert client.render(_grid(1), with_outcome=True).was_sent is True


def test_a_non_429_http_error_still_releases_the_slot(clock, wire):
    """Only a 429 means "slow down": any other failure gives the slot back."""
    client = build_driver(_rw_cloud("test_rw_500"))
    wire.answers = [_response(500)]
    first = client.render(_grid(1), with_outcome=True)
    assert (first.success, first.was_sent, first.throttled) == (False, False, False)

    clock.t += 1.0
    assert client.render(_grid(1), with_outcome=True).was_sent is True


# --- device keys ------------------------------------------------------------------


def _digest(value: str) -> str:
    """The credential fingerprint, computed independently: PBKDF2-HMAC-SHA256, fixed salt."""
    return hashlib.pbkdf2_hmac("sha256", value.encode(), b"fiestaboard-device-key", 100_000).hex()


class TestDeviceKey:
    def test_a_local_board_is_its_host_and_port(self):
        assert BoardClient(api_key="test_key", host="192.0.2.10").device_key() == "vestaboard-local:192.0.2.10:7000"
        assert (
            BoardClient(api_key="test_key", host="192.0.2.10", port=7001).device_key()
            == "vestaboard-local:192.0.2.10:7001"
        )

    def test_an_rw_cloud_board_is_a_hash_of_its_key_never_the_key(self):
        key = BoardClient(api_key="test_secret_rw", use_cloud=True).device_key()
        assert key.startswith("vestaboard-rw-cloud:")
        assert "test_secret_rw" not in key
        assert key.split(":", 1)[1] == _digest("test_secret_rw")[:16]

    def test_a_note_array_cloud_board_is_a_hash_of_its_token_never_the_token(self):
        client = BoardClient(api_key="test_secret_tok", use_cloud=True, note_array_token="test_secret_tok")
        key = client.device_key()
        assert key.startswith("vestaboard-note-array-cloud:")
        assert "test_secret_tok" not in key

    def test_a_local_note_array_is_its_tiles(self):
        tiles = [
            {"row": 0, "col": 1, "host": "192.0.2.12", "local_api_key": "test_key"},
            {"row": 0, "col": 0, "host": "192.0.2.11", "local_api_key": "test_key", "port": 7001},
        ]
        assert NoteArrayLocalClient(tiles, 2, 1).device_key() == "note-array-local:192.0.2.11:7001,192.0.2.12:7000"

    def test_a_virtual_board_is_its_board_id(self):
        assert VirtualBoardClient(device_type="flagship", board_id="vb1").device_key() == "virtual:vb1"
