"""End-to-end note-array send -> read round-trip through BoardClient.

This is the cohesive feature test for the note-array epic (#1167, issue #1179).
The individual merged issues each ship focused unit tests; this module ties the
whole path together in one deterministic flow:

    1. A ``send_characters`` POST hits the note-array Cloud API URL
       (``cloud.vestaboard.com``) with the ``X-Vestaboard-Token`` header and a
       ``{"characters": grid}`` body — never the legacy RW Cloud URL.
    2. A subsequent ``read_current_message`` parses that exact grid back.
    3. Transition parameters are absent from the note-array POST body even when
       a strategy is passed (note arrays do not support transitions).
    4. A second immediate send is throttled by the 15s client-side rate limit
       (driven by an injected monotonic clock — no real time/network).

The HTTP layer is mocked with a small **stateful** transport that ties POST and
GET together (POST stores the grid; GET returns it as a Cloud-shaped
``currentMessage.layout`` JSON string), mirroring the real Cloud API contract
and the ``requests``-patching approach used in ``tests/test_board_client.py``.
"""

import json as _json
from unittest.mock import Mock, patch

import pytest

from src.board_client import (
    BoardClient,
    _note_array_last_send,
)

# Note-array geometry under test: a 4-wide single row → 3 rows × 60 cols.
NOTES_WIDE = 4
NOTES_TALL = 1
ROWS = NOTES_TALL * 3
COLS = NOTES_WIDE * 15
TOKEN = "e2e-note-array-token"

CLOUD_NOTE_ARRAY_URL = BoardClient.CLOUD_NOTE_ARRAY_API_URL
RW_CLOUD_URL = BoardClient.CLOUD_API_URL


@pytest.fixture(autouse=True)
def _reset_throttle():
    """Reset the module-level note-array throttle so each test is isolated."""
    _note_array_last_send.clear()
    yield
    _note_array_last_send.clear()


def _make_grid(fill: int = 0) -> list[list[int]]:
    return [[fill] * COLS for _ in range(ROWS)]


class _FakeCloud:
    """Stateful in-memory stand-in for ``cloud.vestaboard.com``.

    POST stores the posted ``characters`` grid; GET returns it in the real
    Cloud read shape (``{"currentMessage": {"layout": "<json>", "id": ...}}``)
    so the client's own parser round-trips it back to a grid. Records every
    request so tests can assert URL, headers, and body.
    """

    def __init__(self):
        self.stored_grid: list[list[int]] | None = None
        self.posts: list[dict] = []
        self.gets: list[dict] = []

    def post(self, url, headers=None, json=None, timeout=None):
        # ``json`` mirrors the ``requests.post(..., json=payload)`` kwarg name.
        body = json
        self.posts.append({"url": url, "headers": headers, "json": body})
        # The Cloud API body is {"characters": grid}.
        self.stored_grid = [row[:] for row in body["characters"]]
        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json = Mock(return_value={"ok": True})
        return resp

    def get(self, url, headers=None, timeout=None):
        self.gets.append({"url": url, "headers": headers})
        grid = self.stored_grid if self.stored_grid is not None else _make_grid()
        layout = _json.dumps(grid)
        resp = Mock()
        resp.raise_for_status = Mock()
        resp.json = Mock(return_value={"currentMessage": {"layout": layout, "id": "msg-1"}})
        return resp


def _make_client(time_func=None) -> BoardClient:
    return BoardClient(
        api_key=TOKEN,
        use_cloud=True,
        skip_unchanged=True,
        note_array_token=TOKEN,
        notes_wide=NOTES_WIDE,
        notes_tall=NOTES_TALL,
        _time_func=time_func,
    )


class TestNoteArrayEndToEnd:
    """One cohesive send -> read round trip exercising the whole note-array path."""

    def test_full_send_read_roundtrip_with_constraints(self):
        """Send a grid, read it back, and verify URL/header/body + no transitions + throttle.

        This single flow is the feature's acceptance check:
          - POST targets cloud.vestaboard.com (not rw.vestaboard.com) with the
            X-Vestaboard-Token header and a {"characters": grid} body.
          - GET parses the stored layout back to the identical grid.
          - The POST body carries no transition params even though a strategy
            was requested.
          - A second send 5s later (clock injected) is throttled and never POSTs.
        """
        fake = _FakeCloud()
        # Injected clock: first send at t=0, throttle check on second send at t=5.
        clock_values = iter([0.0, 5.0])
        client = _make_client(time_func=lambda: next(clock_values, 5.0))

        sent_grid = _make_grid()
        sent_grid[0][0] = 1
        sent_grid[2][59] = 71  # extremes of the 3×60 grid

        with patch("src.board_client.requests.post", side_effect=fake.post):
            success, was_sent = client.send_characters(sent_grid, strategy="column", step_interval_ms=500, step_size=2)

        # 1. Send succeeded and actually went out.
        assert (success, was_sent) == (True, True)
        assert len(fake.posts) == 1
        post = fake.posts[0]

        # 2. URL is the note-array Cloud API, never the legacy RW Cloud URL.
        assert post["url"] == CLOUD_NOTE_ARRAY_URL
        assert post["url"] != RW_CLOUD_URL

        # 3. Token header is present and correct.
        assert post["headers"]["X-Vestaboard-Token"] == TOKEN
        assert post["headers"]["Content-Type"] == "application/json"

        # 4. Body is exactly {"characters": grid} — no transition keys.
        assert post["json"] == {"characters": sent_grid}
        assert "strategy" not in post["json"]
        assert "step_interval_ms" not in post["json"]
        assert "step_size" not in post["json"]

        # 5. Read it back — the parsed layout equals the grid we sent.
        with patch("src.board_client.requests.get", side_effect=fake.get):
            read_grid = client.read_current_message()

        assert read_grid == sent_grid
        assert len(read_grid) == ROWS
        assert all(len(row) == COLS for row in read_grid)

        # Read used the same note-array URL + token header.
        assert len(fake.gets) == 1
        assert fake.gets[0]["url"] == CLOUD_NOTE_ARRAY_URL
        assert fake.gets[0]["headers"]["X-Vestaboard-Token"] == TOKEN

        # 6. A second, immediate send (t=5 < 15s) is throttled — no new POST.
        second_grid = _make_grid(fill=2)
        with patch("src.board_client.requests.post", side_effect=fake.post) as second_post:
            ok, was_sent2 = client.send_characters(second_grid)

        assert (ok, was_sent2) == (True, False)
        second_post.assert_not_called()
        assert len(fake.posts) == 1  # still just the first send

    def test_send_after_throttle_window_goes_through_and_read_reflects_it(self):
        """After the 15s window elapses a new send lands and a read reflects the latest grid."""
        fake = _FakeCloud()
        # t=0 first send, t=20 (>15s) second send.
        clock_values = iter([0.0, 20.0])
        client = _make_client(time_func=lambda: next(clock_values, 20.0))

        first = _make_grid(fill=3)
        second = _make_grid(fill=7)

        with patch("src.board_client.requests.post", side_effect=fake.post):
            assert client.send_characters(first) == (True, True)
            assert client.send_characters(second) == (True, True)

        assert len(fake.posts) == 2

        with patch("src.board_client.requests.get", side_effect=fake.get):
            read_grid = client.read_current_message()

        # The board now reflects the most recent (second) send.
        assert read_grid == second
