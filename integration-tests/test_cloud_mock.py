"""Integration tests for the note-array Cloud API mock server.

Exercises ``integration-tests/mock-cloud/server.py`` (the stdlib-only mock of
``https://cloud.vestaboard.com/``) and the round-trip behaviour of
``src.board_client.BoardClient`` against it.

The mock server is started in-process on an ephemeral port via a pytest
fixture, so these tests run standalone (``pytest integration-tests/test_cloud_mock.py``)
with only ``pytest`` + ``httpx`` installed — no Docker, no real network.

``BoardClient`` is pointed at the mock by monkeypatching its class-level
``CLOUD_NOTE_ARRAY_API_URL`` constant, mirroring the established integration
pattern (real HTTP to a local mock instead of ``requests`` patching).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Iterator
from http.server import HTTPServer
from pathlib import Path
from threading import Thread

import httpx
import pytest

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent

# Default note-array geometry used by the mock + these tests (a 2×2 grid).
ROWS = 6
COLS = 30


def _load_mock_module():
    """Import mock-cloud/server.py as a module (the dir name isn't importable)."""
    server_path = _HERE / "mock-cloud" / "server.py"
    spec = importlib.util.spec_from_file_location("mock_cloud_server", server_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_mock = _load_mock_module()


def _grid(rows: int = ROWS, cols: int = COLS, fill: int = 0) -> list[list[int]]:
    return [[fill] * cols for _ in range(rows)]


@pytest.fixture
def mock_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Start the in-process mock Cloud API on an ephemeral port.

    Yields the base URL (``http://127.0.0.1:<port>/``). The mock is configured
    in strict 6×30 mode (matching the compose/CI ``ROWS``/``COLS`` env) so
    dimension validation is exercised deterministically. State is reset before
    each test via the mock's own ``reset()`` so tests stay isolated.
    """
    monkeypatch.setattr(_mock, "_ROWS", ROWS)
    monkeypatch.setattr(_mock, "_COLS", COLS)
    monkeypatch.setattr(_mock, "_STRICT_DIMS", True)
    monkeypatch.setattr(_mock, "STATE", _mock.MockCloudState(ROWS, COLS))
    server = HTTPServer(("127.0.0.1", 0), _mock.Handler)
    port = server.server_address[1]
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def client(mock_server: str) -> httpx.Client:
    with httpx.Client(base_url=mock_server, timeout=5.0) as c:
        yield c


_TOKEN_HEADERS = {"X-Vestaboard-Token": "test-tok", "Content-Type": "application/json"}


class TestMockCloudServerPOST:
    def test_post_valid_6x30_grid_returns_200(self, client: httpx.Client) -> None:
        resp = client.post("/", json={"characters": _grid()}, headers=_TOKEN_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_post_stores_grid_readable_via_mock_state(self, client: httpx.Client) -> None:
        grid = _grid()
        grid[0][0] = 1
        grid[5][29] = 71
        resp = client.post("/", json={"characters": grid}, headers=_TOKEN_HEADERS)
        assert resp.status_code == 200

        state = client.get("/mock/state").json()
        assert state["current_grid"] == grid
        assert state["request_count"] == 1

    def test_post_missing_token_returns_401(self, client: httpx.Client) -> None:
        resp = client.post(
            "/",
            json={"characters": _grid()},
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401

    def test_post_wrong_token_still_accepted(self, client: httpx.Client) -> None:
        # The mock validates header *presence*, not the token *value* — value
        # correctness is an app-level concern.
        resp = client.post(
            "/",
            json={"characters": _grid()},
            headers={"X-Vestaboard-Token": "wrong-tok", "Content-Type": "application/json"},
        )
        assert resp.status_code == 200

    def test_post_missing_characters_key_returns_400(self, client: httpx.Client) -> None:
        resp = client.post("/", json={"text": "hello"}, headers=_TOKEN_HEADERS)
        assert resp.status_code == 400

    def test_post_invalid_grid_wrong_dimensions_returns_400(self, client: httpx.Client) -> None:
        # Mock defaults to strict 6×30; a 6×22 grid must be rejected.
        resp = client.post("/", json={"characters": _grid(6, 22)}, headers=_TOKEN_HEADERS)
        assert resp.status_code == 400

    def test_post_invalid_cell_value_returns_400(self, client: httpx.Client) -> None:
        grid = _grid()
        grid[2][7] = 999
        resp = client.post("/", json={"characters": grid}, headers=_TOKEN_HEADERS)
        assert resp.status_code == 400


class TestMockCloudServerGET:
    def test_get_after_post_returns_layout_with_correct_dimensions(self, client: httpx.Client) -> None:
        client.post("/", json={"characters": _grid()}, headers=_TOKEN_HEADERS)
        resp = client.get("/", headers=_TOKEN_HEADERS)
        assert resp.status_code == 200
        layout = json.loads(resp.json()["currentMessage"]["layout"])
        assert len(layout) == ROWS
        assert all(len(row) == COLS for row in layout)

    def test_get_layout_value_matches_posted_grid(self, client: httpx.Client) -> None:
        grid = _grid()
        grid[1][3] = 5
        grid[4][20] = 63
        client.post("/", json={"characters": grid}, headers=_TOKEN_HEADERS)
        resp = client.get("/", headers=_TOKEN_HEADERS)
        layout = json.loads(resp.json()["currentMessage"]["layout"])
        assert layout == grid

    def test_get_missing_token_returns_401(self, client: httpx.Client) -> None:
        resp = client.get("/")
        assert resp.status_code == 401

    def test_get_returns_id_field(self, client: httpx.Client) -> None:
        resp = client.get("/", headers=_TOKEN_HEADERS)
        message_id = resp.json()["currentMessage"]["id"]
        assert isinstance(message_id, str)
        assert message_id

    def test_get_before_any_post_returns_blank_grid(self, client: httpx.Client) -> None:
        client.post("/mock/reset")
        resp = client.get("/", headers=_TOKEN_HEADERS)
        layout = json.loads(resp.json()["currentMessage"]["layout"])
        assert all(cell == 0 for row in layout for cell in row)


class TestMockCloudServerReset:
    def test_reset_clears_grid(self, client: httpx.Client) -> None:
        grid = _grid(fill=10)
        client.post("/", json={"characters": grid}, headers=_TOKEN_HEADERS)
        client.post("/mock/reset")
        resp = client.get("/", headers=_TOKEN_HEADERS)
        layout = json.loads(resp.json()["currentMessage"]["layout"])
        assert all(cell == 0 for row in layout for cell in row)

    def test_reset_resets_request_count(self, client: httpx.Client) -> None:
        client.post("/", json={"characters": _grid(fill=1)}, headers=_TOKEN_HEADERS)
        client.post("/", json={"characters": _grid(fill=2)}, headers=_TOKEN_HEADERS)
        client.post("/mock/reset")
        state = client.get("/mock/state").json()
        assert state["request_count"] == 0


@pytest.fixture
def board_client_module(monkeypatch: pytest.MonkeyPatch, mock_server: str):
    """Import ``src.board_client`` with its Cloud URL redirected to the mock."""
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from src import board_client

    monkeypatch.setattr(board_client.BoardClient, "CLOUD_NOTE_ARRAY_API_URL", mock_server)
    # Reset the module-level note-array send throttle so each test starts clean.
    # Without this, a send in one test leaves a timestamp keyed by note_array_token
    # that throttles the next test's send within the 15s window (the send→read
    # roundtrip would then read a stale grid). Mirrors the autouse reset in
    # tests/test_board_client.py.
    board_client._note_array_last_send.clear()
    return board_client


class TestBoardClientIntegrationWithMock:
    def test_board_client_send_characters_to_mock_succeeds(self, board_client_module) -> None:
        client = board_client_module.BoardClient(
            api_key="tok",
            use_cloud=True,
            note_array_token="tok",
            notes_wide=2,
            notes_tall=2,
        )
        success, was_sent = client.send_characters(_grid(fill=4))
        assert (success, was_sent) == (True, True)

    def test_board_client_read_current_message_from_mock(self, board_client_module, client: httpx.Client) -> None:
        grid = _grid()
        grid[0][0] = 9
        grid[5][29] = 50
        client.post("/", json={"characters": grid}, headers=_TOKEN_HEADERS)

        board = board_client_module.BoardClient(
            api_key="tok",
            use_cloud=True,
            note_array_token="tok",
            notes_wide=2,
            notes_tall=2,
        )
        result = board.read_current_message()
        assert result is not None
        assert len(result) == ROWS
        assert all(len(row) == COLS for row in result)
        assert result == grid

    def test_board_client_send_then_read_roundtrip(self, board_client_module) -> None:
        grid = _grid()
        grid[2][10] = 33
        grid[3][15] = 17

        board = board_client_module.BoardClient(
            api_key="tok",
            use_cloud=True,
            note_array_token="tok",
            notes_wide=2,
            notes_tall=2,
        )
        success, _ = board.send_characters(grid)
        assert success is True

        result = board.read_current_message()
        assert result == grid

    def test_board_client_missing_token_raises(self, board_client_module) -> None:
        # An empty api_key is rejected end-to-end, confirming token enforcement.
        with pytest.raises(ValueError, match="api_key is required"):
            board_client_module.BoardClient(
                api_key="",
                use_cloud=True,
                note_array_token="",
                notes_wide=2,
                notes_tall=2,
            )
